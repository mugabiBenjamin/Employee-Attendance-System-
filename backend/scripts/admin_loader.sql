-- Insert the user
INSERT INTO users (
        employee_id,
        email,
        password_hash,
        first_name,
        last_name,
        hire_date
    )
VALUES (
        'EMP000001',
        'admin@example.com',
        '$2b$12$S3NXHSN0T2BaWE1r9lVWdOIDuqVfGqDKe03I7mZ/ZkC727dzEg2jq',
        'System',
        'Admin',
        CURRENT_DATE
    );
-- Get the new user_id
SELECT user_id
FROM users
WHERE email = 'admin@example.com';
-- Get role_id of Admin or Super_Admin
SELECT role_id
FROM roles
WHERE role_name = 'Super_Admin';
-- Assign the role (replace 1 and 5 with actual user_id and role_id)
INSERT INTO user_roles (user_id, role_id, assigned_at)
VALUES (1, 5, CURRENT_TIMESTAMP);