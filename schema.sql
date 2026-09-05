-- Job Application Tracker schema

CREATE TABLE IF NOT EXISTS applications (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    company       TEXT NOT NULL,
    role          TEXT NOT NULL,
    date_applied  DATE,
    deadline      DATE,
    priority      INTEGER CHECK (priority IN (1, 2, 3)),
    stage         TEXT NOT NULL CHECK (
        stage IN (
            'Applied', 'Assessment', 'Interview',
            'Offer', 'Accepted', 'Rejected', 'Withdrawn'
        )
    ),
    location      TEXT,
    url           TEXT,
    created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS links (
    id     INTEGER PRIMARY KEY AUTOINCREMENT,
    label  TEXT NOT NULL,
    url    TEXT NOT NULL
);

-- Keep updated_at fresh whenever a row changes
CREATE TRIGGER IF NOT EXISTS trg_applications_updated_at
AFTER UPDATE ON applications
FOR EACH ROW
BEGIN
    UPDATE applications SET updated_at = CURRENT_TIMESTAMP WHERE id = OLD.id;
END;
