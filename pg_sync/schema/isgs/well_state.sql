-- Layer 2: Well-State Tables
-- Populated by synthesizer.py from Layer 1 (completion_reports + child tables).
-- well_headers is defined here but populated externally from the state regulatory DB.

CREATE TABLE IF NOT EXISTS isgs.well_headers (
    id                  BIGINT PRIMARY KEY,     -- 10-digit API
    api_uwi_10          TEXT,
    operator            TEXT,
    well_name           TEXT,
    county              TEXT,
    state               TEXT DEFAULT 'IL',
    surface_latitude    DOUBLE PRECISION,
    surface_longitude   DOUBLE PRECISION,
    lease_sign          BOOLEAN,
    plss_loc            TEXT,
    section             INTEGER,
    township            TEXT,
    range               TEXT
);

CREATE TABLE IF NOT EXISTS isgs.sidetracks (
    id                          BIGINT PRIMARY KEY,  -- 12-digit API
    sidetrack_number            TEXT,
    well_id                     BIGINT,              -- 10-digit API → well_headers.id
    type                        TEXT,
    permit_number               TEXT,
    permit_date                 DATE,
    spud_date                   DATE,
    comp_date                   DATE,
    first_prod_date             DATE,
    plug_date                   DATE,
    tvd                         DOUBLE PRECISION,
    md                          DOUBLE PRECISION,
    pbtd                        DOUBLE PRECISION,
    status                      TEXT,
    status_date                 DATE,
    bottom_hole_latitude        DOUBLE PRECISION,
    bottom_hole_longitude       DOUBLE PRECISION,
    primary_sidetrack           BOOLEAN DEFAULT TRUE,
    rotary_tools_from           DOUBLE PRECISION,
    rotary_tools_to             DOUBLE PRECISION,
    cable_tools_from            DOUBLE PRECISION,
    cable_tools_to              DOUBLE PRECISION,
    logs_run                    BOOLEAN,
    last_log_date               DATE,
    cored                       BOOLEAN,
    core_from                   DOUBLE PRECISION,
    core_to                     DOUBLE PRECISION,
    dst                         BOOLEAN,
    dst_zone                    TEXT,
    not_converted_permit_expired BOOLEAN,
    not_drilled_permit_expired  BOOLEAN,
    source_report_name          TEXT,
    source_report_date          DATE,
    last_synthesized_at         TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS isgs.casings (
    id                  SERIAL PRIMARY KEY,
    sidetrack_id        BIGINT NOT NULL,
    type                TEXT NOT NULL,
    hole_size           DOUBLE PRECISION,
    out_diam            DOUBLE PRECISION,
    in_diam             DOUBLE PRECISION,
    weight              DOUBLE PRECISION,
    grade               TEXT,
    cem_type            TEXT,
    cem_density         DOUBLE PRECISION,
    cem_vol             DOUBLE PRECISION,
    cem_top_md          DOUBLE PRECISION,
    cem_top_method      TEXT,
    tvd                 DOUBLE PRECISION,
    pulled              TEXT,
    is_liner            BOOLEAN,
    source_report_name  TEXT,
    last_synthesized_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE (sidetrack_id, type)
);

CREATE TABLE IF NOT EXISTS isgs.logs (
    id                  SERIAL PRIMARY KEY,
    sidetrack_id        BIGINT NOT NULL,
    log_date            DATE,
    log_type            TEXT,
    source_report_name  TEXT,
    UNIQUE (sidetrack_id, log_date, log_type)
);

CREATE TABLE IF NOT EXISTS isgs.completions (
    id                  SERIAL PRIMARY KEY,
    sidetrack_id        BIGINT NOT NULL,
    source_report_name  TEXT NOT NULL,
    form                TEXT,
    lithology           TEXT,
    open_hole_from      DOUBLE PRECISION,
    open_hole_to        DOUBLE PRECISION,
    perf_from           DOUBLE PRECISION,
    perf_to             DOUBLE PRECISION,
    perf_shots          TEXT,
    treatment_from      DOUBLE PRECISION,
    treatment_to        DOUBLE PRECISION,
    treatment           TEXT,
    treatment_amnt      TEXT,
    treatment_date      DATE,
    UNIQUE (sidetrack_id, source_report_name)
);

CREATE TABLE IF NOT EXISTS isgs.production_testing (
    id                  SERIAL PRIMARY KEY,
    sidetrack_id        BIGINT NOT NULL,
    source_report_name  TEXT NOT NULL,
    form                TEXT,
    test_date           DATE,
    test_length         TEXT,
    pre_test_prod       TEXT,
    post_test_prod      TEXT,
    gas_prod            DOUBLE PRECISION,
    oil_prod            DOUBLE PRECISION,
    water_prod          DOUBLE PRECISION,
    UNIQUE (sidetrack_id, source_report_name)
);

CREATE TABLE IF NOT EXISTS isgs.injection_testing (
    id                  SERIAL PRIMARY KEY,
    sidetrack_id        BIGINT NOT NULL,
    source_report_name  TEXT NOT NULL,
    fluid_source        TEXT,
    form                TEXT,
    inj_date            DATE,
    fluid_type          TEXT,
    water_inj_rate      DOUBLE PRECISION,
    water_psi           DOUBLE PRECISION,
    gas_inj_rate        DOUBLE PRECISION,
    gas_press           DOUBLE PRECISION,
    UNIQUE (sidetrack_id, source_report_name)
);

CREATE TABLE IF NOT EXISTS isgs.tubings (
    id                  SERIAL PRIMARY KEY,
    sidetrack_id        BIGINT NOT NULL,
    source_report_name  TEXT,
    type                TEXT,
    out_diam            DOUBLE PRECISION,
    in_diam             DOUBLE PRECISION,
    weight              DOUBLE PRECISION,
    grade               TEXT,
    tvd                 DOUBLE PRECISION,
    md                  DOUBLE PRECISION
);

CREATE TABLE IF NOT EXISTS isgs.packers (
    id                  SERIAL PRIMARY KEY,
    sidetrack_id        BIGINT NOT NULL,
    source_report_name  TEXT,
    type                TEXT,
    depth               DOUBLE PRECISION
);

CREATE TABLE IF NOT EXISTS isgs.additional_cement (
    id                  SERIAL PRIMARY KEY,
    casing_id           INTEGER REFERENCES isgs.casings(id),
    sidetrack_id        BIGINT,
    source_report_name  TEXT,
    install_method      TEXT,
    type                TEXT,
    density             DOUBLE PRECISION,
    vol                 DOUBLE PRECISION,
    top_md              DOUBLE PRECISION,
    bot_md              DOUBLE PRECISION
);

-- Placeholder: populated when plugging reports are added (Phase 2)
CREATE TABLE IF NOT EXISTS isgs.plugs (
    id                  SERIAL PRIMARY KEY,
    sidetrack_id        BIGINT NOT NULL,
    source_report_name  TEXT,
    plug_date           DATE,
    plug_type           TEXT,
    top_md              DOUBLE PRECISION,
    bot_md              DOUBLE PRECISION
);
