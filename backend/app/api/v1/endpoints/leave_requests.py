from fastapi import APIRouter, Depends, HTTPException, status
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
from app.models.user_roles import UserRoles
from app.models.roles import Roles
from app.core.permissions import check_permissions
from app.core.security import get_current_active_user
from app.core.config import settings
from app.core.enums import Permission
from app.schemas.leave_request import LeaveRequestCreate, LeaveRequestOut
from app.schemas.leave_balance import LeaveBalanceOut
from app.schemas.leave_policy import LeavePolicyCreate, LeavePolicyOut
from app.schemas.holiday_calendar import HolidayCalendarCreate, HolidayCalendarOut
from app.schemas.leave_approval_workflow import LeaveApprovalWorkflowOut, LeaveApprovalWorkflowCreate
import logging
from fastapi.responses import FileResponse
import csv
import io
import os
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/leave-requests", tags=["Leave Requests"])

async def is_manager_or_hr_or_admin(db: AsyncSession, user: Users) -> bool:
    try:
        query = select(UserRoles).join(Roles).where(
            UserRoles.user_id == user.user_id,
            UserRoles.is_active == True,
            Roles.role_name.in_(["Manager", "HR", "Admin", "Super_Admin"]),
            Roles.is_active == True
        )
        result = await db.execute(query)
        return result.scalar_one_or_none() is not None
    except Exception as e:
        logger.error(f"Error checking role for user_id {user.user_id}: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error checking user role")

@router.post("/", response_model=LeaveRequestOut, status_code=status.HTTP_201_CREATED, summary="Create leave request")
async def create_leave_request(
    leave_request: LeaveRequestCreate,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_active_user)
) -> LeaveRequestOut:
    try:
        query = select(LeavePolicies).where(LeavePolicies.leave_type == leave_request.leave_type, LeavePolicies.is_active == True)
        result = await db.execute(query)
        policy = result.scalar_one_or_none()
        if not policy:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid leave type")

        query = select(LeaveBalances).where(LeaveBalances.user_id == current_user.user_id, LeaveBalances.leave_type == leave_request.leave_type)
        result = await db.execute(query)
        balance = result.scalar_one_or_none()
        if not balance:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No leave balance for this type")

        days_requested = (leave_request.end_date - leave_request.start_date).days + 1
        if balance.used_days + days_requested > balance.allocated_days:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Insufficient leave balance")

        query = select(HolidayCalendar).where(HolidayCalendar.holiday_date.between(leave_request.start_date, leave_request.end_date), HolidayCalendar.is_active == True)
        result = await db.execute(query)
        if result.scalars().first():
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Requested dates overlap with holidays")

        db_request = LeaveRequests(
            user_id=current_user.user_id,
            leave_type=leave_request.leave_type,
            start_date=leave_request.start_date,
            end_date=leave_request.end_date,
            days_requested=days_requested,
            reason=leave_request.reason,
            status=leave_request.status,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
            is_active=True
        )
        db.add(db_request)
        await db.commit()
        await db.refresh(db_request)

        logger.info(f"Leave request created, leave_id: {db_request.leave_id}, user_id: {current_user.user_id}")
        return LeaveRequestOut.model_validate(db_request)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating leave request for user_id {current_user.user_id}: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error creating leave request")

@router.get("/history", response_model=List[LeaveRequestOut], summary="Get leave request history")
async def get_leave_requests(
    user_id: Optional[int] = None,
    skip: int = 0,
    limit: int = settings.DEFAULT_PAGE_SIZE,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_active_user)
) -> List[LeaveRequestOut]:
    try:
        if user_id and not await is_manager_or_hr_or_admin(db, current_user):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to view others' leave requests")

        query = select(LeaveRequests).where(LeaveRequests.is_active == True)
        if user_id:
            query = query.where(LeaveRequests.user_id == user_id)
        else:
            query = query.where(LeaveRequests.user_id == current_user.user_id)
        query = query.offset(skip).limit(limit)
        result = await db.execute(query)
        requests = result.scalars().all()

        logger.info(f"Retrieved {len(requests)} leave requests for user_id: {user_id or current_user.user_id}")
        return [LeaveRequestOut.model_validate(req) for req in requests]

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving leave requests: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error retrieving leave requests")

@router.get("/balance", response_model=List[LeaveBalanceOut], summary="Get leave balance")
async def get_leave_balance(
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_active_user)
) -> List[LeaveBalanceOut]:
    try:
        query = select(LeaveBalances).where(LeaveBalances.user_id == current_user.user_id)
        result = await db.execute(query)
        balances = result.scalars().all()

        logger.info(f"Retrieved leave balances for user_id: {current_user.user_id}")
        return [LeaveBalanceOut.model_validate(balance) for balance in balances]

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving leave balance for user_id {current_user.user_id}: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error retrieving leave balance")

@router.post("/policies", response_model=LeavePolicyOut, status_code=status.HTTP_201_CREATED, summary="Create leave policy")
async def create_leave_policy(
    policy: LeavePolicyCreate,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_active_user)
) -> LeavePolicyOut:
    try:
        has_permission = await check_permissions([Permission.MANAGE_LEAVE_POLICIES.value], current_user, db)
        if not has_permission and not await is_manager_or_hr_or_admin(db, current_user):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to create leave policies")

        query = select(LeavePolicies).where(LeavePolicies.leave_type == policy.leave_type, LeavePolicies.is_active == True)
        result = await db.execute(query)
        if result.scalar_one_or_none():
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Leave type already exists")

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

        logger.info(f"Leave policy created, policy_id: {db_policy.policy_id}, leave_type: {db_policy.leave_type}")
        return LeavePolicyOut.model_validate(db_policy)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating leave policy: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error creating leave policy")

@router.get("/policies", response_model=List[LeavePolicyOut], summary="List leave policies")
async def get_leave_policies(
    skip: int = 0,
    limit: int = settings.DEFAULT_PAGE_SIZE,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_active_user)
) -> List[LeavePolicyOut]:
    try:
        has_permission = await check_permissions([Permission.VIEW_LEAVE_POLICIES.value], current_user, db)
        if not has_permission and not await is_manager_or_hr_or_admin(db, current_user):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to view leave policies")

        query = select(LeavePolicies).where(LeavePolicies.is_active == True).offset(skip).limit(limit)
        result = await db.execute(query)
        policies = result.scalars().all()

        logger.info(f"Retrieved {len(policies)} leave policies")
        return [LeavePolicyOut.model_validate(policy) for policy in policies]

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving leave policies: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error retrieving leave policies")

@router.post("/holidays", response_model=HolidayCalendarOut, status_code=status.HTTP_201_CREATED, summary="Create holiday")
async def create_holiday(
    holiday: HolidayCalendarCreate,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_active_user)
) -> HolidayCalendarOut:
    try:
        has_permission = await check_permissions([Permission.MANAGE_HOLIDAYS.value], current_user, db)
        if not has_permission and not await is_manager_or_hr_or_admin(db, current_user):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to create holidays")

        query = select(HolidayCalendar).where(HolidayCalendar.holiday_date == holiday.holiday_date, HolidayCalendar.is_active == True)
        result = await db.execute(query)
        if result.scalar_one_or_none():
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Holiday already exists for this date")

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

        logger.info(f"Holiday created, holiday_id: {db_holiday.holiday_id}, date: {db_holiday.holiday_date}")
        return HolidayCalendarOut.model_validate(db_holiday)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating holiday: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error creating holiday")

@router.get("/holidays", response_model=List[HolidayCalendarOut], summary="List holidays")
async def get_holidays(
    skip: int = 0,
    limit: int = settings.DEFAULT_PAGE_SIZE,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_active_user)
) -> List[HolidayCalendarOut]:
    try:
        has_permission = await check_permissions([Permission.VIEW_HOLIDAYS.value], current_user, db)
        if not has_permission and not await is_manager_or_hr_or_admin(db, current_user):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to view holidays")

        query = select(HolidayCalendar).where(HolidayCalendar.is_active == True).offset(skip).limit(limit)
        result = await db.execute(query)
        holidays = result.scalars().all()

        logger.info(f"Retrieved {len(holidays)} holidays")
        return [HolidayCalendarOut.model_validate(holiday) for holiday in holidays]

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving holidays: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error retrieving holidays")

@router.put("/approve/{leave_id}", response_model=LeaveApprovalWorkflowOut, summary="Approve/reject leave request")
async def approve_reject_leave_request(
    leave_id: int,
    approval: LeaveApprovalWorkflowCreate,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_active_user)
) -> LeaveApprovalWorkflowOut:
    try:
        has_permission = await check_permissions([Permission.APPROVE_LEAVE_REQUESTS.value], current_user, db)
        if not has_permission and not await is_manager_or_hr_or_admin(db, current_user):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to approve leave requests")

        if approval.status not in ["approved", "rejected", "under_review"]:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid status")

        query = select(LeaveRequests).where(LeaveRequests.leave_id == leave_id, LeaveRequests.is_active == True)
        result = await db.execute(query)
        leave_request = result.scalar_one_or_none()
        if not leave_request:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Leave request not found")

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

        leave_request.status = approval.status
        leave_request.approved_by = current_user.user_id
        leave_request.approved_at = datetime.now(timezone.utc)
        leave_request.updated_at = datetime.now(timezone.utc)

        if approval.status == "approved":
            query = select(LeaveBalances).where(LeaveBalances.user_id == leave_request.user_id, LeaveBalances.leave_type == leave_request.leave_type)
            result = await db.execute(query)
            balance = result.scalar_one_or_none()
            if balance:
                balance.used_days += leave_request.days_requested
                balance.updated_at = datetime.now(timezone.utc)
                db.add(balance)

        db.add(leave_request)
        await db.commit()
        await db.refresh(db_approval)

        logger.info(f"Leave request {leave_id} {approval.status} by user_id: {current_user.user_id}")
        return LeaveApprovalWorkflowOut.model_validate(db_approval)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error processing leave request {leave_id}: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error processing leave request")

@router.get("/export/csv", response_model=None, summary="Export leave requests as CSV")
async def export_leave_requests_csv(
    start_date: date = date.today().replace(day=1),
    end_date: date = date.today(),
    user_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_active_user)
) -> FileResponse:
    try:
        if user_id and not await is_manager_or_hr_or_admin(db, current_user):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to export others' leave requests")

        query = select(LeaveRequests).where(LeaveRequests.start_date >= start_date, LeaveRequests.end_date <= end_date, LeaveRequests.is_active == True)
        if user_id:
            query = query.where(LeaveRequests.user_id == user_id)
        else:
            query = query.where(LeaveRequests.user_id == current_user.user_id)
        result = await db.execute(query)
        requests = result.scalars().all()

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["Leave ID", "User ID", "Leave Type", "Start Date", "End Date", "Days Requested", "Status", "Reason", "Created At", "Updated At"])
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
                req.created_at,
                req.updated_at
            ])

        output.seek(0)
        filename = f"leave_requests_{user_id or current_user.user_id}_{start_date}_to_{end_date}.csv"
        with open(filename, "w") as f:
            f.write(output.getvalue())

        logger.info(f"Leave requests CSV exported for user_id: {user_id or current_user.user_id}")
        return FileResponse(filename, media_type="text/csv", filename=filename)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error exporting leave requests CSV: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error exporting leave requests CSV")
    finally:
        if os.path.exists(filename):
            os.remove(filename)

@router.get("/export/pdf", response_model=None, summary="Export leave requests as PDF")
async def export_leave_requests_pdf(
    start_date: date = date.today().replace(day=1),
    end_date: date = date.today(),
    user_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_active_user)
) -> FileResponse:
    try:
        if user_id and not await is_manager_or_hr_or_admin(db, current_user):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to export others' leave requests")

        query = select(LeaveRequests).where(LeaveRequests.start_date >= start_date, LeaveRequests.end_date <= end_date, LeaveRequests.is_active == True)
        if user_id:
            query = query.where(LeaveRequests.user_id == user_id)
        else:
            query = query.where(LeaveRequests.user_id == current_user.user_id)
        result = await db.execute(query)
        requests = result.scalars().all()

        filename = f"leave_requests_{user_id or current_user.user_id}_{start_date}_to_{end_date}.pdf"
        doc = SimpleDocTemplate(filename, pagesize=letter)
        elements = []

        data = [["Leave ID", "User ID", "Leave Type", "Start Date", "End Date", "Days Requested", "Status", "Reason", "Created At", "Updated At"]]
        for req in requests:
            data.append([
                str(req.leave_id),
                str(req.user_id),
                req.leave_type,
                str(req.start_date),
                str(req.end_date),
                str(req.days_requested),
                req.status,
                req.reason or "",
                str(req.created_at),
                str(req.updated_at)
            ])

        table = Table(data)
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 12),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
            ('GRID', (0, 0), (-1, -1), 1, colors.black)
        ]))
        elements.append(table)

        doc.build(elements)

        logger.info(f"Leave requests PDF exported for user_id: {user_id or current_user.user_id}")
        return FileResponse(filename, media_type="application/pdf", filename=filename)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error exporting leave requests PDF: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error exporting leave requests PDF")
    finally:
        if os.path.exists(filename):
            os.remove(filename)