-- Insert admin user
INSERT INTO users (
        email,
        password_hash,
        first_name,
        last_name,
        hire_date,
        employee_type,
        salary,
        is_active
    )
VALUES (
        'admin@company.com',
        '$2b$12$UiyOvPEc3Quok3yhNsSH8OtPTK40boxjeGtvTwyjASd1J0N.XjsxS',
        'System',
        'Administrator',
        CURRENT_DATE,
        'full_time',
        100000.00,
        TRUE
    );
-- Assign Super_Admin role
INSERT INTO user_roles (user_id, role_id, assigned_at, is_active)
SELECT u.user_id,
    r.role_id,
    CURRENT_TIMESTAMP,
    TRUE
FROM users u,
    roles r
WHERE u.email = 'admin@company.com'
    AND r.role_name = 'Super_Admin';
-- Assign to IT department
INSERT INTO user_departments (user_id, department_id, assigned_at, is_primary)
SELECT u.user_id,
    d.department_id,
    CURRENT_TIMESTAMP,
    TRUE
FROM users u,
    departments d
WHERE u.email = 'admin@company.com'
    AND d.department_name = 'IT';