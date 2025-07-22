from datetime import datetime, time, timezone
from typing import List, Optional
from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select
from app.models.user import User
from app.models.user_departments import UserDepartment
from app.models.employee_hierarchy import EmployeeHierarchy
from app.models.employee_emergency_contacts import EmployeeEmergencyContact
from app.schemas.user import UserCreate, UserUpdate, UserOut, UserDepartmentCreate, UserDepartmentOut, EmployeeHierarchyCreate, EmployeeHierarchyOut, EmployeeEmergencyContactCreate, EmployeeEmergencyContactOut
from app.core.security import get_password_hash
from app.core.config import settings
import logging

logger = logging.getLogger(__name__)

async def get_user_by_id(db: AsyncSession, user_id: int) -> Optional[User]:
    query = select(User).where(User.user_id == user_id, User.is_active == True, User.deleted_at == None)
    result = await db.execute(query)
    return result.scalar_one_or_none()

async def get_user_by_email(db: AsyncSession, email: str) -> Optional[User]:
    query = select(User).where(User.email == email, User.is_active == True, User.deleted_at == None)
    result = await db.execute(query)
    return result.scalar_one_or_none()

async def create_user(db: AsyncSession, user_create: UserCreate, department_id: Optional[int] = None, manager_id: Optional[int] = None) -> UserOut:
    try:
        # Check for existing email
        query = select(User).where(User.email == user_create.email)
        result = await db.execute(query)
        if result.scalar_one_or_none():
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email already registered")
        
        # Validate employee_type
        valid_employee_types = ["full_time", "part_time", "contract", "intern", "temporary"]
        if user_create.employee_type not in valid_employee_types:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, 
                              detail=f"Invalid employee type. Must be one of {valid_employee_types}")
        
        # Generate employee_id using sequence
        query = select("nextval('employee_id_seq')")
        result = await db.execute(query)
        sequence_value = result.scalar_one()
        employee_id = f"EMP{str(sequence_value).zfill(6)}"
        
        hashed_password = get_password_hash(user_create.password)
        db_user = User(
            **user_create.model_dump(exclude={"password"}, exclude_none=True),
            password_hash=hashed_password,
            employee_id=employee_id,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc)
        )
        
        db.add(db_user)
        await db.commit()
        await db.refresh(db_user)
        
        # Assign to department if provided
        if department_id:
            user_department = UserDepartment(
                user_id=db_user.user_id,
                department_id=department_id,
                is_primary=True,
                assigned_at=datetime.now(timezone.utc)
            )
            db.add(user_department)
        
        # Create hierarchy entry if manager_id provided
        if manager_id:
            if manager_id == db_user.user_id:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, 
                                  detail="User cannot be their own manager")
            manager = await get_user_by_id(db, manager_id)
            if not manager:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Manager not found")
            
            hierarchy = EmployeeHierarchy(
                employee_id=db_user.user_id,
                manager_id=manager_id,
                level=1,
                effective_from=datetime.now(timezone.utc).date(),
                created_at=datetime.now(timezone.utc)
            )
            db.add(hierarchy)
        
        await db.commit()
        await db.refresh(db_user)
        
        logger.info(f"User created, user_id {db_user.user_id}, employee_id {db_user.employee_id}")
        return UserOut.model_validate(db_user)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating user: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
                          detail="Error creating user")

async def update_user(db: AsyncSession, user_id: int, user_update: UserUpdate, 
                    department_id: Optional[int] = None, manager_id: Optional[int] = None) -> UserOut:
    try:
        user = await get_user_by_id(db, user_id)
        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
        
        update_data = user_update.model_dump(exclude_none=True)
        if "password" in update_data:
            update_data["password_hash"] = get_password_hash(update_data.pop("password"))
        
        # Validate employee_type if provided
        if "employee_type" in update_data:
            valid_employee_types = ["full_time", "part_time", "contract", "intern", "temporary"]
            if update_data["employee_type"] not in valid_employee_types:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, 
                                  detail=f"Invalid employee type. Must be one of {valid_employee_types}")
        
        for key, value in update_data.items():
            setattr(user, key, value)
        
        # Update department assignment
        if department_id:
            query = select(UserDepartment).where(
                UserDepartment.user_id == user_id,
                UserDepartment.is_primary == True
            )
            result = await db.execute(query)
            user_dept = result.scalar_one_or_none()
            
            if user_dept:
                user_dept.department_id = department_id
                user_dept.assigned_at = datetime.now(timezone.utc)
                db.add(user_dept)
            else:
                user_department = UserDepartment(
                    user_id=user_id,
                    department_id=department_id,
                    is_primary=True,
                    assigned_at=datetime.now(timezone.utc)
                )
                db.add(user_department)
        
        # Update hierarchy
        if manager_id is not None:
            if manager_id == user_id:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, 
                                  detail="User cannot be their own manager")
            manager = await get_user_by_id(db, manager_id)
            if not manager and manager_id != 0:  # Allow nullifying manager
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Manager not found")
            
            query = select(EmployeeHierarchy).where(
                EmployeeHierarchy.employee_id == user_id,
                EmployeeHierarchy.effective_to == None
            )
            result = await db.execute(query)
            hierarchy = result.scalar_one_or_none()
            
            if hierarchy:
                hierarchy.effective_to = datetime.now(timezone.utc).date()
                db.add(hierarchy)
            
            if manager_id:
                new_hierarchy = EmployeeHierarchy(
                    employee_id=user_id,
                    manager_id=manager_id,
                    level=1,
                    effective_from=datetime.now(timezone.utc).date(),
                    created_at=datetime.now(timezone.utc)
                )
                db.add(new_hierarchy)
        
        user.updated_at = datetime.now(timezone.utc)
        await db.commit()
        await db.refresh(user)
        
        logger.info(f"User updated, user_id {user_id}")
        return UserOut.model_validate(user)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating user: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
                          detail="Error updating user")

async def delete_user(db: AsyncSession, user_id: int) -> None:
    try:
        user = await get_user_by_id(db, user_id)
        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
        
        user.is_active = False
        user.deleted_at = datetime.now(timezone.utc)
        await db.commit()
        
        logger.info(f"User soft deleted, user_id {user_id}")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting user: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
                          detail="Error deleting user")

async def get_users(db: AsyncSession, skip: int = 0, limit: int = settings.DEFAULT_PAGE_SIZE) -> List[UserOut]:
    try:
        query = select(User).where(User.is_active == True, User.deleted_at == None).offset(skip).limit(limit)
        result = await db.execute(query)
        users = result.scalars().all()
        
        logger.info(f"Retrieved {len(users)} active users")
        return [UserOut.model_validate(user) for user in users]
    except Exception as e:
        logger.error(f"Error retrieving users: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
                          detail="Error retrieving users")

async def create_user_department(db: AsyncSession, user_department: UserDepartmentCreate) -> UserDepartmentOut:
    try:
        query = select(UserDepartment).where(
            UserDepartment.user_id == user_department.user_id,
            UserDepartment.department_id == user_department.department_id
        )
        result = await db.execute(query)
        if result.scalar_one_or_none():
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, 
                              detail="User already assigned to this department")
        
        db_user_dept = UserDepartment(
            **user_department.model_dump(),
            assigned_at=datetime.now(timezone.utc)
        )
        db.add(db_user_dept)
        await db.commit()
        await db.refresh(db_user_dept)
        
        logger.info(f"User department created, user_id {db_user_dept.user_id}, department_id {db_user_dept.department_id}")
        return UserDepartmentOut.model_validate(db_user_dept)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating user department: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
                          detail="Error creating user department")

async def create_employee_hierarchy(db: AsyncSession, hierarchy: EmployeeHierarchyCreate) -> EmployeeHierarchyOut:
    try:
        if hierarchy.employee_id == hierarchy.manager_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, 
                              detail="User cannot be their own manager")
        
        employee = await get_user_by_id(db, hierarchy.employee_id)
        manager = await get_user_by_id(db, hierarchy.manager_id)
        if not employee or not manager:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, 
                              detail="Employee or manager not found")
        
        if hierarchy.level < 1 or hierarchy.level > 10:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, 
                              detail="Hierarchy level must be between 1 and 10")
        
        # End existing hierarchy if active
        query = select(EmployeeHierarchy).where(
            EmployeeHierarchy.employee_id == hierarchy.employee_id,
            EmployeeHierarchy.effective_to == None
        )
        result = await db.execute(query)
        existing_hierarchy = result.scalar_one_or_none()
        if existing_hierarchy:
            existing_hierarchy.effective_to = datetime.now(timezone.utc).date()
            db.add(existing_hierarchy)
        
        db_hierarchy = EmployeeHierarchy(
            **hierarchy.model_dump(),
            created_at=datetime.now(timezone.utc)
        )
        db.add(db_hierarchy)
        await db.commit()
        await db.refresh(db_hierarchy)
        
        logger.info(f"Employee hierarchy created, employee_id {hierarchy.employee_id}, manager_id {hierarchy.manager_id}")
        return EmployeeHierarchyOut.model_validate(db_hierarchy)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating employee hierarchy: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
                          detail="Error creating employee hierarchy")

async def create_employee_emergency_contact(db: AsyncSession, contact: EmployeeEmergencyContactCreate) -> EmployeeEmergencyContactOut:
    try:
        user = await get_user_by_id(db, contact.user_id)
        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
        
        # If setting as primary, unset other primary contacts
        if contact.is_primary:
            query = select(EmployeeEmergencyContact).where(
                EmployeeEmergencyContact.user_id == contact.user_id,
                EmployeeEmergencyContact.is_primary == True
            )
            result = await db.execute(query)
            existing_primary = result.scalars().all()
            for primary_contact in existing_primary:
                primary_contact.is_primary = False
                db.add(primary_contact)
        
        db_contact = EmployeeEmergencyContact(
            **contact.model_dump(),
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc)
        )
        db.add(db_contact)
        await db.commit()
        await db.refresh(db_contact)
        
        logger.info(f"Emergency contact created for user_id {contact.user_id}, contact_id {db_contact.contact_id}")
        return EmployeeEmergencyContactOut.model_validate(db_contact)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating emergency contact: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
                          detail="Error creating emergency contact")