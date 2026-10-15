-- HTTP idempotency uses the same MySQL transaction as submission and extension writes.
CREATE TABLE IF NOT EXISTS oj_run_request (
    u_id BIGINT NOT NULL,
    request_key VARCHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    payload_hash CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    s_id BIGINT NULL,
    expires_at TIMESTAMP(3) NOT NULL,
    PRIMARY KEY (u_id, request_key),
    INDEX idx_run_request_expiry (expires_at)
) ENGINE=InnoDB;
