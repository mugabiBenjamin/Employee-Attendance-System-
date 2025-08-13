from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List, Optional
from datetime import datetime, timezone, date
from app.core.database import get_db
from app.models.leave_requests import LeaveRequests
from app.models.leave_balances import LeaveBalances
from app.models.leave_policies import LeavePolicies
from app.models.holiday_calendar import HolidayCalendar
from app.models.leave_approval_workflow import LeaveApprovalWorkflow
from app.models.users import Users
from app.core.permissions import (
    check_permissions,
    require_permissions,
    require_hr_permissions
)
from app.core.security import get_current_user
from app.core.config import settings
from app.core.enums import Permission, LeaveRequestStatus, LeaveType
from app.schemas.leave_request import LeaveRequestCreate, LeaveRequestOut
from app.schemas.leave_balance import LeaveBalanceOut
from app.schemas.leave_policy import LeavePolicyCreate, LeavePolicyOut
from app.schemas.holiday_calendar import HolidayCalendarCreate, HolidayCalendarOut
from app.schemas.leave_approval_workflow import LeaveApprovalWorkflowOut
from pydantic import BaseModel, ConfigDict
import logging
import csv
import io
import os
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle
from slowapi import Limiter
from slowapi.util import get_remote_address

logger = logging.getLogger(__name__)

# Initialize rate limiter
limiter = Limiter(key_func=get_remote_address)

router = APIRouter(prefix="/leave-requests", tags=["Leave Requests"])

class LeaveApprovalUpdate(BaseModel):
    status: str  # 'approved' or 'rejected'
    comments: Optional[str] = None
    model_config = ConfigDict(from_attributes=True)

@router.post("/", 
            response_model=LeaveRequestOut, 
            status_code=status.HTTP_201_CREATED,
            dependencies=[Depends(require_permissions([Permission.REQUEST_LEAVE]))],
            summary="Create leave request")
@limiter.limit("5/minute")
async def create_leave_request(
    request: Request,
    leave_request: LeaveRequestCreate,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user)
) -> LeaveRequestOut:
    try:
        # Validate leave type exists in enum
        if leave_request.leave_type not in [lt.value for lt in LeaveType]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, 
                detail="Invalid leave type"
            )

        # Check leave policy exists
        query = select(LeavePolicies).where(
            LeavePolicies.leave_type == leave_request.leave_type, 
            LeavePolicies.is_active == True
        )
        result = await db.execute(query)
        policy = result.scalar_one_or_none()
        if not policy:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, 
                detail="Leave policy not found for this type"
            )

        # Check leave balance
        query = select(LeaveBalances).where(
            LeaveBalances.user_id == current_user.user_id, 
            LeaveBalances.leave_type == leave_request.leave_type
        )
        result = await db.execute(query)
        balance = result.scalar_one_or_none()
        if not balance:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, 
                detail="No leave balance found for this type"
            )

        # Calculate days requested
        days_requested = (leave_request.end_date - leave_request.start_date).days + 1
        
        # Check sufficient balance
        if balance.used_days + days_requested > balance.allocated_days:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, 
                detail="Insufficient leave balance"
            )

        # Check for holiday conflicts
        query = select(HolidayCalendar).where(
            HolidayCalendar.holiday_date.between(leave_request.start_date, leave_request.end_date),
            HolidayCalendar.is_active == True
        )
        result = await db.execute(query)
        if result.scalars().first():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, 
                detail="Leave dates conflict with holidays"
            )

        # Check for overlapping leave requests
        query = select(LeaveRequests).where(
            LeaveRequests.user_id == current_user.user_id,
            LeaveRequests.status.in_([LeaveRequestStatus.APPROVED, LeaveRequestStatus.UNDER_REVIEW]),
            LeaveRequests.is_active == True,
            LeaveRequests.start_date <= leave_request.end_date,
            LeaveRequests.end_date >= leave_request.start_date
        )
        result = await db.execute(query)
        if result.scalars().first():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, 
                detail="Leave dates overlap with existing request"
            )

        db_request = LeaveRequests(
            user_id=current_user.user_id,
            leave_type=leave_request.leave_type,
            start_date=leave_request.start_date,
            end_date=leave_request.end_date,
            days_requested=days_requested,
            reason=leave_request.reason,
            status=LeaveRequestStatus.UNDER_REVIEW,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
            is_active=True
        )
        db.add(db_request)
        await db.commit()
        await db.refresh(db_request)

        logger.info(f"Leave request created: {db_request.leave_id} for user: {current_user.user_id}")
        return LeaveRequestOut.model_validate(db_request)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating leave request: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
            detail="Error creating leave request"
        )

@router.get("/history", 
            response_model=List[LeaveRequestOut],
            dependencies=[Depends(require_permissions([Permission.REQUEST_LEAVE]))],
            summary="Get leave request history")
async def get_leave_requests(
    user_id: Optional[int] = None,
    skip: int = 0,
    limit: int = settings.DEFAULT_PAGE_SIZE,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user)
) -> List[LeaveRequestOut]:
    try:
        # Check permissions for viewing other users' requests
        if user_id and user_id != current_user.user_id:
            await check_permissions([Permission.VIEW_TEAM_ATTENDANCE], current_user, db)

        query = select(LeaveRequests).where(LeaveRequests.is_active == True)
        target_user_id = user_id if user_id else current_user.user_id
        query = query.where(LeaveRequests.user_id == target_user_id)
        query = query.order_by(LeaveRequests.created_at.desc()).offset(skip).limit(limit)
        
        result = await db.execute(query)
        requests = result.scalars().all()

        logger.info(f"Retrieved {len(requests)} leave requests for user: {target_user_id}")
        return [LeaveRequestOut.model_validate(req) for req in requests]

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving leave requests: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
            detail="Error retrieving leave requests"
        )

@router.get("/balance", 
            response_model=List[LeaveBalanceOut],
            dependencies=[Depends(require_permissions([Permission.VIEW_LEAVE_BALANCE]))],
            summary="Get leave balance")
async def get_leave_balance(
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user)
) -> List[LeaveBalanceOut]:
    try:
        query = select(LeaveBalances).where(LeaveBalances.user_id == current_user.user_id)
        result = await db.execute(query)
        balances = result.scalars().all()

        logger.info(f"Retrieved leave balances for user: {current_user.user_id}")
        return [LeaveBalanceOut.model_validate(balance) for balance in balances]

    except Exception as e:
        logger.error(f"Error retrieving leave balance: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
            detail="Error retrieving leave balance"
        )

@router.post("/policies", 
            response_model=LeavePolicyOut, 
            status_code=status.HTTP_201_CREATED,
            dependencies=[Depends(require_permissions([Permission.MANAGE_LEAVE_POLICIES]))],
            summary="Create leave policy")
async def create_leave_policy(
    policy: LeavePolicyCreate,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user)
) -> LeavePolicyOut:
    try:
        # Validate leave type exists in enum
        if policy.leave_type not in [lt.value for lt in LeaveType]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, 
                detail="Invalid leave type"
            )

        # Check if policy already exists
        query = select(LeavePolicies).where(
            LeavePolicies.leave_type == policy.leave_type, 
            LeavePolicies.is_active == True
        )
        result = await db.execute(query)
        if result.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, 
                detail="Leave policy already exists for this type"
            )

        db_policy = LeavePolicies(
            employee_type="all",
            leave_type=policy.leave_type,
            annual_allocation=int(policy.annual_allocation),
            max_consecutive_days=policy.max_consecutive_days,
            requires_approval=True,
            approval_levels=1,
            accrual_rate=0,
            effective_from=date.today(),
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
            is_active=True
        )
        db.add(db_policy)
        await db.commit()
        await db.refresh(db_policy)

        logger.info(f"Leave policy created: {db_policy.policy_id}")
        return LeavePolicyOut.model_validate(db_policy)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating leave policy: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
            detail="Error creating leave policy"
        )

@router.get("/policies", 
            response_model=List[LeavePolicyOut],
            dependencies=[Depends(require_permissions([Permission.MANAGE_LEAVE_POLICIES]))],
            summary="List leave policies")
async def get_leave_policies(
    skip: int = 0,
    limit: int = settings.DEFAULT_PAGE_SIZE,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user)
) -> List[LeavePolicyOut]:
    try:
        query = select(LeavePolicies).where(
            LeavePolicies.is_active == True
        ).order_by(LeavePolicies.created_at.desc()).offset(skip).limit(limit)
        
        result = await db.execute(query)
        policies = result.scalars().all()

        logger.info(f"Retrieved {len(policies)} leave policies")
        return [LeavePolicyOut.model_validate(policy) for policy in policies]

    except Exception as e:
        logger.error(f"Error retrieving leave policies: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
            detail="Error retrieving leave policies"
        )

@router.post("/holidays", 
            response_model=HolidayCalendarOut, 
            status_code=status.HTTP_201_CREATED,
            dependencies=[Depends(require_hr_permissions())],
            summary="Create holiday")
async def create_holiday(
    holiday: HolidayCalendarCreate,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user)
) -> HolidayCalendarOut:
    try:
        # Check if holiday already exists for this date
        query = select(HolidayCalendar).where(
            HolidayCalendar.holiday_date == holiday.holiday_date, 
            HolidayCalendar.is_active == True
        )
        result = await db.execute(query)
        if result.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, 
                detail="Holiday already exists for this date"
            )

        db_holiday = HolidayCalendar(
            holiday_name=holiday.holiday_name,
            holiday_date=holiday.holiday_date,
            is_recurring=holiday.is_recurring,
            applies_to_all=holiday.applies_to_all,
            department_id=holiday.department_id,
            year=holiday.year,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
            is_active=True
        )
        db.add(db_holiday)
        await db.commit()
        await db.refresh(db_holiday)

        logger.info(f"Holiday created: {db_holiday.holiday_id}")
        return HolidayCalendarOut.model_validate(db_holiday)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating holiday: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
            detail="Error creating holiday"
        )

@router.get("/holidays", 
            response_model=List[HolidayCalendarOut],
            summary="List holidays")
async def get_holidays(
    skip: int = 0,
    limit: int = settings.DEFAULT_PAGE_SIZE,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user)
) -> List[HolidayCalendarOut]:
    try:
        query = select(HolidayCalendar).where(
            HolidayCalendar.is_active == True
        ).order_by(HolidayCalendar.holiday_date.desc()).offset(skip).limit(limit)
        
        result = await db.execute(query)
        holidays = result.scalars().all()

        logger.info(f"Retrieved {len(holidays)} holidays")
        return [HolidayCalendarOut.model_validate(holiday) for holiday in holidays]

    except Exception as e:
        logger.error(f"Error retrieving holidays: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
            detail="Error retrieving holidays"
        )

@router.put("/approve/{leave_id}", 
            response_model=LeaveApprovalWorkflowOut,
            dependencies=[Depends(require_permissions([Permission.APPROVE_LEAVE]))],
            summary="Approve/reject leave request")
async def approve_reject_leave_request(
    leave_id: int,
    approval: LeaveApprovalUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user)
) -> LeaveApprovalWorkflowOut:
    try:
        # Validate status
        if approval.status not in [LeaveRequestStatus.APPROVED, LeaveRequestStatus.REJECTED]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, 
                detail="Invalid status. Must be 'approved' or 'rejected'"
            )

        # Get leave request
        query = select(LeaveRequests).where(
            LeaveRequests.leave_id == leave_id, 
            LeaveRequests.is_active == True
        )
        result = await db.execute(query)
        leave_request = result.scalar_one_or_none()
        if not leave_request:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, 
                detail="Leave request not found"
            )

        if leave_request.status != LeaveRequestStatus.UNDER_REVIEW:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, 
                detail="Leave request has already been processed"
            )

        # Create approval workflow entry
        db_approval = LeaveApprovalWorkflow(
            leave_id=leave_id,
            approver_id=current_user.user_id,
            level=1,
            status=approval.status,
            comments=approval.comments,
            action_taken_at=datetime.now(timezone.utc),
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc)
        )
        db.add(db_approval)

        # Update leave request
        leave_request.status = approval.status
        leave_request.approved_by = current_user.user_id
        leave_request.approved_at = datetime.now(timezone.utc)
        leave_request.updated_at = datetime.now(timezone.utc)

        # Update leave balance if approved
        if approval.status == LeaveRequestStatus.APPROVED:
            query = select(LeaveBalances).where(
                LeaveBalances.user_id == leave_request.user_id, 
                LeaveBalances.leave_type == leave_request.leave_type
            )
            result = await db.execute(query)
            balance = result.scalar_one_or_none()
            if balance:
                balance.used_days += leave_request.days_requested
                balance.updated_at = datetime.now(timezone.utc)
                db.add(balance)

        db.add(leave_request)
        await db.commit()
        await db.refresh(db_approval)

        logger.info(f"Leave request {leave_id} {approval.status} by user: {current_user.user_id}")
        return LeaveApprovalWorkflowOut.model_validate(db_approval)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error processing leave request {leave_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
            detail="Error processing leave request"
        )

@router.get("/export/csv", 
            dependencies=[Depends(require_permissions([Permission.REQUEST_LEAVE]))],
            summary="Export leave requests as CSV")
async def export_leave_requests_csv(
    start_date: date = date.today().replace(day=1),
    end_date: date = date.today(),
    user_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user)
) -> FileResponse:
    filename = None
    try:
        # Check permissions for other users' data
        if user_id and user_id != current_user.user_id:
            await check_permissions([Permission.VIEW_TEAM_ATTENDANCE], current_user, db)

        query = select(LeaveRequests).where(
            LeaveRequests.start_date >= start_date,
            LeaveRequests.end_date <= end_date,
            LeaveRequests.is_active == True
        )
        
        target_user_id = user_id if user_id else current_user.user_id
        query = query.where(LeaveRequests.user_id == target_user_id)
        query = query.order_by(LeaveRequests.created_at.desc())
        
        result = await db.execute(query)
        requests = result.scalars().all()

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow([
            "Leave ID", "User ID", "Leave Type", "Start Date", "End Date", 
            "Days Requested", "Status", "Reason", "Created At"
        ])
        
        for req in requests:
            writer.writerow([
                req.leave_id,
                req.user_id,
                req.leave_type,
                req.start_date,
                req.end_date,
                req.days_requested,
                req.status,
                req.reason or "",
                req.created_at
            ])

        filename = f"leave_requests_{target_user_id}_{start_date}_to_{end_date}.csv"
        with open(filename, "w", newline='', encoding='utf-8') as f:
            f.write(output.getvalue())

        logger.info(f"Leave requests CSV exported for user: {target_user_id}")
        return FileResponse(
            filename, 
            media_type="text/csv", 
            filename=f"leave_requests_export_{start_date}_to_{end_date}.csv"
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error exporting leave requests CSV: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
            detail="Error exporting leave requests CSV"
        )
    finally:
        if filename and os.path.exists(filename):
            os.remove(filename)

@router.get("/export/pdf", 
            dependencies=[Depends(require_permissions([Permission.REQUEST_LEAVE]))],
            summary="Export leave requests as PDF")
async def export_leave_requests_pdf(
    start_date: date = date.today().replace(day=1),
    end_date: date = date.today(),
    user_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user)
) -> FileResponse:
    filename = None
    try:
        # Check permissions for other users' data
        if user_id and user_id != current_user.user_id:
            await check_permissions([Permission.VIEW_TEAM_ATTENDANCE], current_user, db)

        query = select(LeaveRequests).where(
            LeaveRequests.start_date >= start_date,
            LeaveRequests.end_date <= end_date,
            LeaveRequests.is_active == True
        )
        
        target_user_id = user_id if user_id else current_user.user_id
        query = query.where(LeaveRequests.user_id == target_user_id)
        query = query.order_by(LeaveRequests.created_at.desc())
        
        result = await db.execute(query)
        requests = result.scalars().all()

        filename = f"leave_requests_{target_user_id}_{start_date}_to_{end_date}.pdf"
        doc = SimpleDocTemplate(filename, pagesize=letter)
        elements = []

        data = [[
            "Leave ID", "User ID", "Leave Type", "Start Date", "End Date", 
            "Days", "Status", "Reason"
        ]]
        
        for req in requests:
            data.append([
                str(req.leave_id),
                str(req.user_id),
                req.leave_type,
                str(req.start_date),
                str(req.end_date),
                str(req.days_requested),
                req.status,
                req.reason[:30] + "..." if req.reason and len(req.reason) > 30 else req.reason or ""
            ])

        table = Table(data)
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 9),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
            ('GRID', (0, 0), (-1, -1), 1, colors.black)
        ]))
        elements.append(table)

        doc.build(elements)

        logger.info(f"Leave requests PDF exported for user: {target_user_id}")
        return FileResponse(
            filename, 
            media_type="application/pdf", 
            filename=f"leave_requests_export_{start_date}_to_{end_date}.pdf"
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error exporting leave requests PDF: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
            detail="Error exporting leave requests PDF"
        )
    finally:
        if filename and os.path.exists(filename):
            os.remove(filename)