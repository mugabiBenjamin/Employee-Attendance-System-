from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from typing import List, Optional
from pydantic import BaseModel, ConfigDict
from datetime import datetime, timezone, date
from app.core.database import AsyncSessionLocal
from app.models.leave_requests import LeaveRequests
from app.models.leave_balances import LeaveBalances
from app.models.leave_policies import LeavePolicies
from app.models.holiday_calendar import HolidayCalendar
from app.models.leave_approval_workflow import LeaveApprovalWorkflow
from app.models.users import Users
from app.models.user_roles import UserRoles
from app.models.roles import Roles
from app.core.security import check_user_permission
from app.core.config import settings
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

class LeaveRequestCreate(BaseModel):
    """Schema for creating a new leave request."""
    leave_type: str
    start_date: date
    end_date: date
    reason: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)

class LeaveRequestOut(BaseModel):
    """Schema for leave request output."""
    request_id: int
    user_id: int
    leave_type: str
    start_date: date
    end_date: date
    reason: Optional[str]
    status: str
    created_at: datetime
    updated_at: datetime
    is_active: bool

    model_config = ConfigDict(from_attributes=True)

class LeaveBalanceOut(BaseModel):
    """Schema for leave balance output."""
    user_id: int
    leave_type: str
    balance: float
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)

class LeavePolicyCreate(BaseModel):
    """Schema for creating a new leave policy."""
    leave_type: str
    annual_allocation: float
    max_consecutive_days: Optional[int] = None
    description: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)

class LeavePolicyOut(BaseModel):
    """Schema for leave policy output."""
    policy_id: int
    leave_type: str
    annual_allocation: float
    max_consecutive_days: Optional[int]
    description: Optional[str]
    created_at: datetime
    updated_at: datetime
    is_active: bool

    model_config = ConfigDict(from_attributes=True)

class HolidayCreate(BaseModel):
    """Schema for creating a new holiday."""
    name: str
    date: date
    description: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)

class HolidayOut(BaseModel):
    """Schema for holiday output."""
    holiday_id: int
    name: str
    date: date
    description: Optional[str]
    created_at: datetime
    updated_at: datetime
    is_active: bool

    model_config = ConfigDict(from_attributes=True)

class LeaveApprovalUpdate(BaseModel):
    """Schema for updating leave approval status."""
    status: str  # 'approved' or 'rejected'
    comments: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)

class LeaveApprovalOut(BaseModel):
    """Schema for leave approval workflow output."""
    approval_id: int
    request_id: int
    approver_id: int
    status: str
    comments: Optional[str]
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)

async def get_db() -> AsyncSession:
    """Dependency to provide an async database session."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception as e:
            logger.error(f"Database session error: {str(e)}")
            await session.rollback()
            raise
        finally:
            await session.close()

async def get_current_active_user(db: AsyncSession = Depends(get_db)) -> Users:
    """Dependency to get the current active user."""
    query = select(Users).where(Users.is_active == True, Users.deleted_at == None)
    result = await db.execute(query)
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not authenticated")
    return user

async def is_manager_or_hr_or_admin(db: AsyncSession, user: Users) -> bool:
    """
    Check if the user has Manager, HR, Admin, or Super_Admin role.

    Args:
        db: Async database session.
        user: Current user object.

    Returns:
        bool: True if user has required role, False otherwise.
    """
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

@router.post("/", response_model=LeaveRequestOut, status_code=status.HTTP_201_CREATED, summary="Create leave request", description="Submit a new leave request.")
async def create_leave_request(
    leave_request: LeaveRequestCreate,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_active_user)
) -> LeaveRequestOut:
    """
    Create a new leave request.

    Args:
        leave_request: Leave request data.
        db: Async database session.
        current_user: Current authenticated user.

    Returns:
        LeaveRequestOut: Created leave request details.

    Raises:
        HTTPException: If leave policy not found, insufficient balance, or dates overlap with holidays.
    """
    try:
        query = select(LeavePolicies).where(
            LeavePolicies.leave_type == leave_request.leave_type,
            LeavePolicies.is_active == True
        )
        result = await db.execute(query)
        policy = result.scalar_one_or_none()
        if not policy:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid leave type")

        query = select(LeaveBalances).where(
            LeaveBalances.user_id == current_user.user_id,
            LeaveBalances.leave_type == leave_request.leave_type
        )
        result = await db.execute(query)
        balance = result.scalar_one_or_none()
        if not balance:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No leave balance for this type")

        days_requested = (leave_request.end_date - leave_request.start_date).days + 1
        if balance.balance < days_requested:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Insufficient leave balance")

        query = select(HolidayCalendar).where(
            HolidayCalendar.date.between(leave_request.start_date, leave_request.end_date),
            HolidayCalendar.is_active == True
        )
        result = await db.execute(query)
        if result.scalars().first():
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Requested dates overlap with holidays")

        db_request = LeaveRequests(
            user_id=current_user.user_id,
            leave_type=leave_request.leave_type,
            start_date=leave_request.start_date,
            end_date=leave_request.end_date,
            reason=leave_request.reason,
            status="pending",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
            is_active=True
        )
        db.add(db_request)
        await db.commit()
        await db.refresh(db_request)

        logger.info(f"Leave request created, request_id: {db_request.request_id}, user_id: {current_user.user_id}")
        return LeaveRequestOut.model_validate(db_request)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating leave request for user_id {current_user.user_id}: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error creating leave request")

@router.get("/history", response_model=List[LeaveRequestOut], summary="Get leave request history", description="Retrieve leave request history for the current user or team (manager/HR/admin).")
async def get_leave_requests(
    user_id: Optional[int] = None,
    skip: int = 0,
    limit: int = settings.DEFAULT_PAGE_SIZE,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_active_user)
) -> List[LeaveRequestOut]:
    """
    Get paginated leave request history.

    Args:
        user_id: Optional user ID to filter requests (manager/HR/admin only).
        skip: Number of records to skip.
        limit: Maximum number of records to return.
        db: Async database session.
        current_user: Current authenticated user.

    Returns:
        List[LeaveRequestOut]: List of leave requests.

    Raises:
        HTTPException: If user lacks permission or an error occurs.
    """
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

@router.get("/balance", response_model=List[LeaveBalanceOut], summary="Get leave balance", description="Retrieve leave balance for the current user.")
async def get_leave_balance(
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_active_user)
) -> List[LeaveBalanceOut]:
    """
    Get leave balance for the current user.

    Args:
        db: Async database session.
        current_user: Current authenticated user.

    Returns:
        List[LeaveBalanceOut]: List of leave balances.

    Raises:
        HTTPException: If an error occurs.
    """
    try:
        query = select(LeaveBalances).where(
            LeaveBalances.user_id == current_user.user_id
        )
        result = await db.execute(query)
        balances = result.scalars().all()

        logger.info(f"Retrieved leave balances for user_id: {current_user.user_id}")
        return [LeaveBalanceOut.model_validate(balance) for balance in balances]

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving leave balance for user_id {current_user.user_id}: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error retrieving leave balance")

@router.post("/policies", response_model=LeavePolicyOut, status_code=status.HTTP_201_CREATED, summary="Create leave policy", description="Create a new leave policy. Requires manage_leave_policies permission or admin access.")
async def create_leave_policy(
    policy: LeavePolicyCreate,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_active_user)
) -> LeavePolicyOut:
    """
    Create a new leave policy.

    Args:
        policy: Leave policy creation data.
        db: Async database session.
        current_user: Current authenticated user.

    Returns:
        LeavePolicyOut: Created leave policy details.

    Raises:
        HTTPException: If user lacks permission or leave type exists.
    """
    try:
        has_permission = await check_user_permission(db, current_user.user_id, "manage_leave_policies")
        if not has_permission and not await is_manager_or_hr_or_admin(db, current_user):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to create leave policies")

        query = select(LeavePolicies).where(
            LeavePolicies.leave_type == policy.leave_type,
            LeavePolicies.is_active == True
        )
        result = await db.execute(query)
        if result.scalar_one_or_none():
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Leave type already exists")

        db_policy = LeavePolicies(
            **policy.model_dump(),
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

@router.get("/policies", response_model=List[LeavePolicyOut], summary="List leave policies", description="Retrieve all leave policies with pagination. Requires view_leave_policies permission or admin access.")
async def get_leave_policies(
    skip: int = 0,
    limit: int = settings.DEFAULT_PAGE_SIZE,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_active_user)
) -> List[LeavePolicyOut]:
    """
    Get paginated list of all leave policies.

    Args:
        skip: Number of records to skip.
        limit: Maximum number of records to return.
        db: Async database session.
        current_user: Current authenticated user.

    Returns:
        List[LeavePolicyOut]: List of leave policies.

    Raises:
        HTTPException: If user lacks permission or an error occurs.
    """
    try:
        has_permission = await check_user_permission(db, current_user.user_id, "view_leave_policies")
        if not has_permission and not await is_manager_or_hr_or_admin(db, current_user):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to view leave policies")

        query = select(LeavePolicies).where(
            LeavePolicies.is_active == True
        ).offset(skip).limit(limit)
        result = await db.execute(query)
        policies = result.scalars().all()

        logger.info(f"Retrieved {len(policies)} leave policies")
        return [LeavePolicyOut.model_validate(policy) for policy in policies]

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving leave policies: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error retrieving leave policies")

@router.post("/holidays", response_model=HolidayOut, status_code=status.HTTP_201_CREATED, summary="Create holiday", description="Create a new holiday. Requires manage_holidays permission or admin access.")
async def create_holiday(
    holiday: HolidayCreate,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_active_user)
) -> HolidayOut:
    """
    Create a new holiday in the calendar.

    Args:
        holiday: Holiday creation data.
        db: Async database session.
        current_user: Current authenticated user.

    Returns:
        HolidayOut: Created holiday details.

    Raises:
        HTTPException: If user lacks permission or holiday exists.
    """
    try:
        has_permission = await check_user_permission(db, current_user.user_id, "manage_holidays")
        if not has_permission and not await is_manager_or_hr_or_admin(db, current_user):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to create holidays")

        query = select(HolidayCalendar).where(
            HolidayCalendar.date == holiday.date,
            HolidayCalendar.is_active == True
        )
        result = await db.execute(query)
        if result.scalar_one_or_none():
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Holiday already exists for this date")

        db_holiday = HolidayCalendar(
            **holiday.model_dump(),
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
            is_active=True
        )
        db.add(db_holiday)
        await db.commit()
        await db.refresh(db_holiday)

        logger.info(f"Holiday created, holiday_id: {db_holiday.holiday_id}, date: {db_holiday.date}")
        return HolidayOut.model_validate(db_holiday)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating holiday: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error creating holiday")

@router.get("/holidays", response_model=List[HolidayOut], summary="List holidays", description="Retrieve all holidays with pagination. Requires view_holidays permission or admin access.")
async def get_holidays(
    skip: int = 0,
    limit: int = settings.DEFAULT_PAGE_SIZE,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_active_user)
) -> List[HolidayOut]:
    """
    Get paginated list of all holidays.

    Args:
        skip: Number of records to skip.
        limit: Maximum number of records to return.
        db: Async database session.
        current_user: Current authenticated user.

    Returns:
        List[HolidayOut]: List of holidays.

    Raises:
        HTTPException: If user lacks permission or an error occurs.
    """
    try:
        has_permission = await check_user_permission(db, current_user.user_id, "view_holidays")
        if not has_permission and not await is_manager_or_hr_or_admin(db, current_user):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to view holidays")

        query = select(HolidayCalendar).where(
            HolidayCalendar.is_active == True
        ).offset(skip).limit(limit)
        result = await db.execute(query)
        holidays = result.scalars().all()

        logger.info(f"Retrieved {len(holidays)} holidays")
        return [HolidayOut.model_validate(holiday) for holiday in holidays]

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving holidays: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error retrieving holidays")

@router.put("/approve/{request_id}", response_model=LeaveApprovalOut, summary="Approve/reject leave request", description="Approve or reject a leave request. Requires approve_leave_requests permission or manager/HR/admin access.")
async def approve_reject_leave_request(
    request_id: int,
    approval: LeaveApprovalUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_active_user)
) -> LeaveApprovalOut:
    """
    Approve or reject a leave request.

    Args:
        request_id: ID of the leave request.
        approval: Approval status and comments.
        db: Async database session.
        current_user: Current authenticated user.

    Returns:
        LeaveApprovalOut: Updated approval details.

    Raises:
        HTTPException: If user lacks permission, request not found, or invalid status.
    """
    try:
        has_permission = await check_user_permission(db, current_user.user_id, "approve_leave_requests")
        if not has_permission and not await is_manager_or_hr_or_admin(db, current_user):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to approve leave requests")

        if approval.status not in ["approved", "rejected"]:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid status")

        query = select(LeaveRequests).where(
            LeaveRequests.request_id == request_id,
            LeaveRequests.is_active == True
        )
        result = await db.execute(query)
        leave_request = result.scalar_one_or_none()
        if not leave_request:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Leave request not found")

        db_approval = LeaveApprovalWorkflow(
            request_id=request_id,
            approver_id=current_user.user_id,
            status=approval.status,
            comments=approval.comments,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc)
        )
        db.add(db_approval)

        leave_request.status = approval.status
        leave_request.updated_at = datetime.now(timezone.utc)

        if approval.status == "approved":
            days = (leave_request.end_date - leave_request.start_date).days + 1
            query = select(LeaveBalances).where(
                LeaveBalances.user_id == leave_request.user_id,
                LeaveBalances.leave_type == leave_request.leave_type
            )
            result = await db.execute(query)
            balance = result.scalar_one_or_none()
            if balance:
                balance.balance -= days
                balance.updated_at = datetime.now(timezone.utc)
                db.add(balance)

        db.add(leave_request)
        await db.commit()
        await db.refresh(db_approval)

        logger.info(f"Leave request {request_id} {approval.status} by user_id: {current_user.user_id}")
        return LeaveApprovalOut.model_validate(db_approval)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error processing leave request {request_id}: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error processing leave request")

@router.get("/export/csv", response_model=None, summary="Export leave requests as CSV", description="Export leave request history as a CSV file.")
async def export_leave_requests_csv(
    start_date: date = date.today().replace(day=1),
    end_date: date = date.today(),
    user_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_active_user)
) -> FileResponse:
    """
    Export leave request history as a CSV file.

    Args:
        start_date: Start date of the period.
        end_date: End date of the period.
        user_id: Optional user ID to filter requests (manager/HR/admin only).
        db: Async database session.
        current_user: Current authenticated user.

    Returns:
        FileResponse: CSV file with leave request history.

    Raises:
        HTTPException: If user lacks permission or an error occurs.
    """
    try:
        if user_id and not await is_manager_or_hr_or_admin(db, current_user):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to export others' leave requests")

        query = select(LeaveRequests).where(
            LeaveRequests.start_date >= start_date,
            LeaveRequests.end_date <= end_date,
            LeaveRequests.is_active == True
        )
        if user_id:
            query = query.where(LeaveRequests.user_id == user_id)
        else:
            query = query.where(LeaveRequests.user_id == current_user.user_id)
        result = await db.execute(query)
        requests = result.scalars().all()

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["Request ID", "User ID", "Leave Type", "Start Date", "End Date", "Status", "Reason", "Created At", "Updated At"])
        for req in requests:
            writer.writerow([
                req.request_id,
                req.user_id,
                req.leave_type,
                req.start_date,
                req.end_date,
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

@router.get("/export/pdf", response_model=None, summary="Export leave requests as PDF", description="Export leave request history as a PDF file.")
async def export_leave_requests_pdf(
    start_date: date = date.today().replace(day=1),
    end_date: date = date.today(),
    user_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_active_user)
) -> FileResponse:
    """
    Export leave request history as a PDF file.

    Args:
        start_date: Start date of the period.
        end_date: End date of the period.
        user_id: Optional user ID to filter requests (manager/HR/admin only).
        db: Async database session.
        current_user: Current authenticated user.

    Returns:
        FileResponse: PDF file with leave request history.

    Raises:
        HTTPException: If user lacks permission or an error occurs.
    """
    try:
        if user_id and not await is_manager_or_hr_or_admin(db, current_user):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to export others' leave requests")

        query = select(LeaveRequests).where(
            LeaveRequests.start_date >= start_date,
            LeaveRequests.end_date <= end_date,
            LeaveRequests.is_active == True
        )
        if user_id:
            query = query.where(LeaveRequests.user_id == user_id)
        else:
            query = query.where(LeaveRequests.user_id == current_user.user_id)
        result = await db.execute(query)
        requests = result.scalars().all()

        filename = f"leave_requests_{user_id or current_user.user_id}_{start_date}_to_{end_date}.pdf"
        doc = SimpleDocTemplate(filename, pagesize=letter)
        elements = []

        data = [["Request ID", "User ID", "Leave Type", "Start Date", "End Date", "Status", "Reason", "Created At", "Updated At"]]
        for req in requests:
            data.append([
                str(req.request_id),
                str(req.user_id),
                req.leave_type,
                str(req.start_date),
                str(req.end_date),
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