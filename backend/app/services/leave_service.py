from typing import List, Optional
from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select
from datetime import date, datetime, timezone
from app.models.leave import LeaveRequest, LeaveBalance, LeavePolicy
from app.models.user import User
from app.schemas.leave import LeaveApprovalWorkflowCreate, LeaveRequestCreate, LeaveRequestUpdate, LeaveRequestOut, LeaveBalanceOut, LeavePolicyOut, LeaveApprovalWorkflowOut, HolidayCalendarOut
from app.core.config import settings
import logging
from app.models.user_departments import UserDepartment
from app.models.holiday_calendar import HolidayCalendar
from app.models.leave_approval_workflow import LeaveApprovalWorkflow

logger = logging.getLogger(__name__)

async def create_leave_request(db: AsyncSession, leave_request: LeaveRequestCreate, current_user: User) -> LeaveRequestOut:
    try:
        # Validate leave_type
        valid_leave_types = ["annual", "sick", "maternity", "paternity", "emergency", "unpaid", "casual", 
                            "compensatory", "bereavement", "leave_of_absence", "public_holiday"]
        if leave_request.leave_type not in valid_leave_types:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, 
                              detail=f"Invalid leave type. Must be one of {valid_leave_types}")
        
        # Validate status
        valid_statuses = ["draft", "under_review", "approved", "rejected", "cancelled", "completed"]
        if leave_request.status not in valid_statuses:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, 
                              detail=f"Invalid status. Must be one of {valid_statuses}")
        
        # Check authorization
        if leave_request.user_id != current_user.user_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, 
                              detail="Not authorized to create leave request for another user")
        
        # Validate against leave policy
        policy = await validate_leave_policy(db, leave_request.user_id, leave_request.leave_type, 
                                          leave_request.start_date, leave_request.days_requested)
        
        # Check holiday conflicts
        await check_holiday_conflicts(db, leave_request.start_date, leave_request.end_date, 
                                   leave_request.user_id)
        
        # Check leave balance
        balance = await check_leave_balance(db, leave_request.user_id, leave_request.leave_type, 
                                         leave_request.days_requested, leave_request.start_date.year)
        
        db_leave = LeaveRequest(
            user_id=leave_request.user_id,
            leave_type=leave_request.leave_type,
            start_date=leave_request.start_date,
            end_date=leave_request.end_date,
            days_requested=leave_request.days_requested,
            reason=leave_request.reason,
            status=leave_request.status,
            attachment_url=leave_request.attachment_url,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc)
        )
        
        # Create approval workflow if required
        if policy.requires_approval:
            workflow = LeaveApprovalWorkflow(
                leave_id=db_leave.leave_id,
                approver_id=current_user.manager_id or current_user.user_id,
                level=1,
                status="under_review",
                created_at=datetime.now(timezone.utc)
            )
            db.add(workflow)
        
        db.add(db_leave)
        await db.commit()
        await db.refresh(db_leave)
        
        logger.info(f"Leave request created for user_id {leave_request.user_id}, leave_id {db_leave.leave_id}")
        return LeaveRequestOut.model_validate(db_leave)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating leave request: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
                          detail="Error creating leave request")

async def update_leave_request(db: AsyncSession, leave_id: int, leave_update: LeaveRequestUpdate, 
                            current_user: User) -> LeaveRequestOut:
    try:
        db_leave = await get_leave_request_by_id(db, leave_id, current_user)
        if not db_leave:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, 
                              detail="Leave request not found")
        
        update_data = leave_update.model_dump(exclude_none=True)
        
        # Validate leave_type if provided
        if "leave_type" in update_data:
            valid_leave_types = ["annual", "sick", "maternity", "paternity", "emergency", "unpaid", 
                               "casual", "compensatory", "bereavement", "leave_of_absence", "public_holiday"]
            if update_data["leave_type"] not in valid_leave_types:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, 
                                  detail=f"Invalid leave type. Must be one of {valid_leave_types}")
        
        # Validate status if provided
        if "status" in update_data:
            valid_statuses = ["draft", "under_review", "approved", "rejected", "cancelled", "completed"]
            if update_data["status"] not in valid_statuses:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, 
                                  detail=f"Invalid status. Must be one of {valid_statuses}")
            
            # Handle approval/rejection
            if update_data["status"] in ["approved", "rejected"]:
                from app.api.deps import is_manager_or_hr
                if not await is_manager_or_hr(db, current_user):
                    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, 
                                      detail="Not authorized to approve/reject leave requests")
                
                update_data["approved_by"] = current_user.user_id
                update_data["approved_at"] = datetime.now(timezone.utc)
                
                # Update leave balance if approved
                if update_data["status"] == "approved":
                    await update_leave_balance(db, db_leave.user_id, db_leave.leave_type, 
                                            db_leave.days_requested, db_leave.start_date.year)
                
                # Update approval workflow
                workflow_query = select(LeaveApprovalWorkflow).where(LeaveApprovalWorkflow.leave_id == leave_id)
                result = await db.execute(workflow_query)
                workflow = result.scalar_one_or_none()
                if workflow:
                    workflow.status = update_data["status"]
                    workflow.action_taken_at = datetime.now(timezone.utc)
                    workflow.comments = update_data.get("comments")
                    db.add(workflow)
        
        # Re-validate policy if leave_type or dates changed
        if any(key in update_data for key in ["leave_type", "start_date", "days_requested"]):
            leave_type = update_data.get("leave_type", db_leave.leave_type)
            start_date = update_data.get("start_date", db_leave.start_date)
            days_requested = update_data.get("days_requested", db_leave.days_requested)
            await validate_leave_policy(db, db_leave.user_id, leave_type, start_date, days_requested)
        
        # Check holiday conflicts if dates changed
        if "start_date" in update_data or "end_date" in update_data:
            start_date = update_data.get("start_date", db_leave.start_date)
            end_date = update_data.get("end_date", db_leave.end_date)
            await check_holiday_conflicts(db, start_date, end_date, db_leave.user_id)
        
        for attr, value in update_data.items():
            setattr(db_leave, attr, value)
        
        db_leave.updated_at = datetime.now(timezone.utc)
        db.add(db_leave)
        await db.commit()
        await db.refresh(db_leave)
        
        logger.info(f"Leave request updated, leave_id {leave_id}")
        return LeaveRequestOut.model_validate(db_leave)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating leave request: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
                          detail="Error updating leave request")

async def get_leave_request_by_id(db: AsyncSession, leave_id: int, current_user: User) -> Optional[LeaveRequestOut]:
    try:
        query = select(LeaveRequest).where(LeaveRequest.leave_id == leave_id)
        result = await db.execute(query)
        db_leave = result.scalar_one_or_none()
        
        if not db_leave:
            return None
        
        if db_leave.user_id != current_user.user_id:
            from app.api.deps import is_manager_or_hr
            if not await is_manager_or_hr(db, current_user):
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, 
                                  detail="Not authorized to view this leave request")
        
        return LeaveRequestOut.model_validate(db_leave)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving leave request: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
                          detail="Error retrieving leave request")

async def get_user_leave_requests(db: AsyncSession, user_id: int, start_date: Optional[date], 
                               end_date: Optional[date], skip: int = 0, 
                               limit: int = settings.DEFAULT_PAGE_SIZE) -> List[LeaveRequestOut]:
    try:
        query = select(LeaveRequest).where(LeaveRequest.user_id == user_id)
        if start_date:
            query = query.where(LeaveRequest.start_date >= start_date)
        if end_date:
            query = query.where(LeaveRequest.end_date <= end_date)
        query = query.offset(skip).limit(limit)
        result = await db.execute(query)
        leave_requests = result.scalars().all()
        
        logger.info(f"Retrieved {len(leave_requests)} leave requests for user_id {user_id}")
        return [LeaveRequestOut.model_validate(lr) for lr in leave_requests]
    except Exception as e:
        logger.error(f"Error retrieving leave requests: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
                          detail="Error retrieving leave requests")

async def get_leave_balance(db: AsyncSession, user_id: int, year: Optional[int]) -> List[LeaveBalanceOut]:
    try:
        query = select(LeaveBalance).where(LeaveBalance.user_id == user_id)
        if year:
            query = query.where(LeaveBalance.year == year)
        result = await db.execute(query)
        balances = result.scalars().all()
        
        logger.info(f"Retrieved {len(balances)} leave balances for user_id {user_id}")
        return [LeaveBalanceOut.model_validate(b) for b in balances]
    except Exception as e:
        logger.error(f"Error retrieving leave balances: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
                          detail="Error retrieving leave balances")

async def validate_leave_policy(db: AsyncSession, user_id: int, leave_type: str, start_date: date, 
                             days_requested: int) -> LeavePolicy:
    try:
        query = select(User).where(User.user_id == user_id)
        result = await db.execute(query)
        user = result.scalar_one_or_none()
        
        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
        
        query = select(LeavePolicy).where(
            LeavePolicy.employee_type == user.employee_type,
            LeavePolicy.leave_type == leave_type,
            LeavePolicy.effective_from <= start_date,
            (LeavePolicy.effective_to >= start_date) | (LeavePolicy.effective_to == None)
        )
        result = await db.execute(query)
        policy = result.scalar_one_or_none()
        
        if not policy:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, 
                              detail=f"No active leave policy found for {leave_type} and employee type {user.employee_type}")
        
        if policy.max_consecutive_days and days_requested > policy.max_consecutive_days:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, 
                              detail=f"Requested days exceed maximum consecutive days ({policy.max_consecutive_days})")
        
        return policy
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error validating leave policy: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
                          detail="Error validating leave policy")

async def check_leave_balance(db: AsyncSession, user_id: int, leave_type: str, days_requested: int, 
                           year: int) -> LeaveBalance:
    try:
        query = select(LeaveBalance).where(
            LeaveBalance.user_id == user_id,
            LeaveBalance.leave_type == leave_type,
            LeaveBalance.year == year
        )
        result = await db.execute(query)
        balance = result.scalar_one_or_none()
        
        if not balance:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, 
                              detail=f"No leave balance found for {leave_type} in {year}")
        
        available_days = balance.allocated_days + balance.carried_forward - balance.used_days
        if days_requested > available_days:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, 
                              detail=f"Insufficient leave balance. Available: {available_days} days")
        
        return balance
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error checking leave balance: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
                          detail="Error checking leave balance")

async def update_leave_balance(db: AsyncSession, user_id: int, leave_type: str, days_used: int, 
                            year: int) -> LeaveBalance:
    try:
        query = select(LeaveBalance).where(
            LeaveBalance.user_id == user_id,
            LeaveBalance.leave_type == leave_type,
            LeaveBalance.year == year
        )
        result = await db.execute(query)
        balance = result.scalar_one_or_none()
        
        if not balance:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, 
                              detail=f"No leave balance found for {leave_type} in {year}")
        
        balance.used_days += days_used
        balance.updated_at = datetime.now(timezone.utc)
        db.add(balance)
        await db.commit()
        await db.refresh(balance)
        
        logger.info(f"Leave balance updated for user_id {user_id}, leave_type {leave_type}")
        return balance
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating leave balance: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
                          detail="Error updating leave balance")

async def check_holiday_conflicts(db: AsyncSession, start_date: date, end_date: date, user_id: int) -> None:
    try:
        query = select(User).where(User.user_id == user_id)
        result = await db.execute(query)
        user = result.scalar_one_or_none()
        
        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
        
        query = select(HolidayCalendar).where(
            HolidayCalendar.holiday_date >= start_date,
            HolidayCalendar.holiday_date <= end_date,
            (HolidayCalendar.applies_to_all == True) | 
            (HolidayCalendar.department_id.in_(
                select(UserDepartment.department_id).where(UserDepartment.user_id == user_id)
            ))
        )
        result = await db.execute(query)
        holidays = result.scalars().all()
        
        if holidays:
            holiday_dates = [h.holiday_date for h in holidays]
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, 
                              detail=f"Leave request conflicts with holidays on {holiday_dates}")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error checking holiday conflicts: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
                          detail="Error checking holiday conflicts")

async def create_leave_approval_workflow(db: AsyncSession, workflow: LeaveApprovalWorkflowCreate, 
                                      current_user: User) -> LeaveApprovalWorkflowOut:
    try:
        query = select(LeaveRequest).where(LeaveRequest.leave_id == workflow.leave_id)
        result = await db.execute(query)
        leave = result.scalar_one_or_none()
        
        if not leave:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, 
                              detail="Leave request not found")
        
        if leave.user_id != current_user.user_id:
            from app.api.deps import is_manager_or_hr
            if not await is_manager_or_hr(db, current_user):
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, 
                                  detail="Not authorized to create approval workflow")
        
        valid_statuses = ["draft", "under_review", "approved", "rejected", "cancelled", "completed"]
        if workflow.status not in valid_statuses:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, 
                              detail=f"Invalid status. Must be one of {valid_statuses}")
        
        if workflow.level < 1 or workflow.level > 5:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, 
                              detail="Approval level must be between 1 and 5")
        
        db_workflow = LeaveApprovalWorkflow(**workflow.model_dump())
        db.add(db_workflow)
        await db.commit()
        await db.refresh(db_workflow)
        
        logger.info(f"Approval workflow created for leave_id {workflow.leave_id}, workflow_id {db_workflow.workflow_id}")
        return LeaveApprovalWorkflowOut.model_validate(db_workflow)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating approval workflow: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
                          detail="Error creating approval workflow")

async def get_holidays(db: AsyncSession, year: Optional[int] = None, department_id: Optional[int] = None, 
                     skip: int = 0, limit: int = settings.DEFAULT_PAGE_SIZE) -> List[HolidayCalendarOut]:
    try:
        query = select(HolidayCalendar)
        if year:
            query = query.where(HolidayCalendar.year == year)
        if department_id:
            query = query.where(
                (HolidayCalendar.department_id == department_id) | 
                (HolidayCalendar.applies_to_all == True)
            )
        query = query.offset(skip).limit(limit)
        result = await db.execute(query)
        holidays = result.scalars().all()
        
        logger.info(f"Retrieved {len(holidays)} holidays")
        return [HolidayCalendarOut.model_validate(h) for h in holidays]
    except Exception as e:
        logger.error(f"Error retrieving holidays: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
                          detail="Error retrieving holidays")