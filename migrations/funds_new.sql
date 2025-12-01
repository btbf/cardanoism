USE cardanoism;

CREATE TABLE funds_new (
    id CHAR(36) NOT NULL PRIMARY KEY,
    title VARCHAR(255) NOT NULL,
    slug VARCHAR(255) NOT NULL,
    label VARCHAR(255) NOT NULL,
    description TEXT,
    status VARCHAR(32),
    currency VARCHAR(16) NOT NULL,
    currency_symbol VARCHAR(8) NOT NULL,
    amount DECIMAL(20,2) NOT NULL,
    launched_at DATETIME(6) NOT NULL,
    awarded_at DATETIME(6),
    assessment_started_at DATETIME(6),
    hero_img_url TEXT,
    banner_img_url TEXT,
    proposals_count INT NOT NULL DEFAULT 0,
    funded_proposals_count INT NOT NULL DEFAULT 0,
    completed_proposals_count INT NOT NULL DEFAULT 0
);
