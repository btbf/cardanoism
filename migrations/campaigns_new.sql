USE cardanoism;

CREATE TABLE campaigns_new (
    id CHAR(36) NOT NULL PRIMARY KEY,
    title VARCHAR(255) NOT NULL,
    title_jp VARCHAR(255),
    slug VARCHAR(255) NOT NULL,
    excerpt TEXT,
    excerpt_jp TEXT,
    amount DECIMAL(20,2) NOT NULL,
    launched_at DATETIME(6),
    awarded_at DATETIME(6),
    color VARCHAR(32),
    label VARCHAR(255) NOT NULL
);
