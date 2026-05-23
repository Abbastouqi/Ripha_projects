-- Enable pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- Users table (auth)
CREATE TABLE IF NOT EXISTS users (
    id            SERIAL PRIMARY KEY,
    username      VARCHAR(100) NOT NULL,
    email         VARCHAR(200) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    role          VARCHAR(20)  DEFAULT 'user',
    is_active     BOOLEAN      DEFAULT TRUE,
    created_at    TIMESTAMP    DEFAULT CURRENT_TIMESTAMP
);

-- Patients table
CREATE TABLE IF NOT EXISTS patients (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    date_of_birth DATE NOT NULL,
    phone VARCHAR(20),
    email VARCHAR(100),
    insurance_id VARCHAR(50),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Doctors table
CREATE TABLE IF NOT EXISTS doctors (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    specialty VARCHAR(100) NOT NULL,
    available_days VARCHAR(50) DEFAULT 'Mon,Tue,Wed,Thu,Fri',
    available_hours VARCHAR(50) DEFAULT '09:00-17:00'
);

-- Appointments table
CREATE TABLE IF NOT EXISTS appointments (
    id SERIAL PRIMARY KEY,
    patient_id INTEGER REFERENCES patients(id),
    doctor_id INTEGER REFERENCES doctors(id),
    datetime TIMESTAMP NOT NULL,
    status VARCHAR(20) DEFAULT 'available',
    reason TEXT,
    workflow_id VARCHAR(50),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Workflows table
CREATE TABLE IF NOT EXISTS workflows (
    id VARCHAR(50) PRIMARY KEY,
    patient_id INTEGER REFERENCES patients(id),
    task_type VARCHAR(50) NOT NULL,
    status VARCHAR(20) DEFAULT 'started',
    steps_json TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Notifications table
CREATE TABLE IF NOT EXISTS notifications (
    id SERIAL PRIMARY KEY,
    patient_id INTEGER REFERENCES patients(id),
    workflow_id VARCHAR(50),
    type VARCHAR(20),
    recipient VARCHAR(100),
    message TEXT,
    sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Sample patients
INSERT INTO patients (name, date_of_birth, phone, email, insurance_id) VALUES
('John Smith',     '1985-03-15', '555-0101', 'john.smith@email.com',     'INS-001234'),
('Sarah Johnson',  '1990-07-22', '555-0102', 'sarah.j@email.com',        'INS-002345'),
('Michael Brown',  '1978-11-08', '555-0103', 'mbrown@email.com',         'INS-003456'),
('Emily Davis',    '1995-01-30', '555-0104', 'emily.d@email.com',        'INS-004567'),
('Robert Wilson',  '1965-09-12', '555-0105', 'rwilson@email.com',        'INS-005678');

-- Sample doctors
INSERT INTO doctors (name, specialty, available_days, available_hours) VALUES
('Dr. Amanda Carter',  'cardiology',    'Mon,Tue,Wed,Thu,Fri', '09:00-17:00'),
('Dr. James Patel',    'neurology',     'Mon,Wed,Fri',          '10:00-16:00'),
('Dr. Lisa Thompson',  'orthopedics',   'Tue,Thu',              '08:00-15:00'),
('Dr. Robert Kim',     'general',       'Mon,Tue,Wed,Thu,Fri', '08:00-18:00');

-- Available appointment slots (next 7 days from schema load date)
INSERT INTO appointments (patient_id, doctor_id, datetime, status, reason) VALUES
(NULL, 1, NOW() + INTERVAL '1 day' + INTERVAL '9 hours',   'available', NULL),
(NULL, 1, NOW() + INTERVAL '1 day' + INTERVAL '11 hours',  'available', NULL),
(NULL, 1, NOW() + INTERVAL '1 day' + INTERVAL '14 hours',  'available', NULL),
(NULL, 1, NOW() + INTERVAL '2 days' + INTERVAL '9 hours',  'available', NULL),
(NULL, 1, NOW() + INTERVAL '2 days' + INTERVAL '14 hours', 'available', NULL),
(NULL, 2, NOW() + INTERVAL '1 day' + INTERVAL '10 hours',  'available', NULL),
(NULL, 2, NOW() + INTERVAL '3 days' + INTERVAL '10 hours', 'available', NULL),
(NULL, 2, NOW() + INTERVAL '5 days' + INTERVAL '13 hours', 'available', NULL),
(NULL, 3, NOW() + INTERVAL '2 days' + INTERVAL '8 hours',  'available', NULL),
(NULL, 3, NOW() + INTERVAL '2 days' + INTERVAL '11 hours', 'available', NULL),
(NULL, 3, NOW() + INTERVAL '4 days' + INTERVAL '8 hours',  'available', NULL),
(NULL, 3, NOW() + INTERVAL '4 days' + INTERVAL '13 hours', 'available', NULL),
(NULL, 4, NOW() + INTERVAL '1 day' + INTERVAL '8 hours',   'available', NULL),
(NULL, 4, NOW() + INTERVAL '1 day' + INTERVAL '10 hours',  'available', NULL),
(NULL, 4, NOW() + INTERVAL '1 day' + INTERVAL '15 hours',  'available', NULL),
(NULL, 4, NOW() + INTERVAL '2 days' + INTERVAL '8 hours',  'available', NULL),
(NULL, 4, NOW() + INTERVAL '3 days' + INTERVAL '11 hours', 'available', NULL),
(NULL, 4, NOW() + INTERVAL '3 days' + INTERVAL '14 hours', 'available', NULL),
(NULL, 4, NOW() + INTERVAL '4 days' + INTERVAL '9 hours',  'available', NULL),
(NULL, 4, NOW() + INTERVAL '5 days' + INTERVAL '10 hours', 'available', NULL);

-- Chat sessions
CREATE TABLE IF NOT EXISTS chat_sessions (
    id VARCHAR(50) PRIMARY KEY,
    title VARCHAR(200) DEFAULT 'New Chat',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Chat messages
CREATE TABLE IF NOT EXISTS chat_messages (
    id SERIAL PRIMARY KEY,
    session_id VARCHAR(50) REFERENCES chat_sessions(id) ON DELETE CASCADE,
    role VARCHAR(20) NOT NULL,
    content TEXT NOT NULL,
    workflow VARCHAR(50) DEFAULT 'general',
    sources_json TEXT DEFAULT '[]',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Uploaded documents registry
CREATE TABLE IF NOT EXISTS uploaded_documents (
    id VARCHAR(50) PRIMARY KEY,
    filename VARCHAR(255) NOT NULL,
    file_type VARCHAR(20),
    chunks_count INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
