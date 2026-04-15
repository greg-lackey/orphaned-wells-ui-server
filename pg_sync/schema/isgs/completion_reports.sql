-- =============================================================================
-- ISGS Completion Reports Schema
-- Mirrors the ISGS regulatory database structure.
-- All data originates from OGRRE-digitized well completion report forms.
-- One row per digitized report in completion_reports.
-- Child tables capture repeating structured rows (logs, perforations, etc.)
-- =============================================================================

CREATE SCHEMA IF NOT EXISTS isgs;

-- ---------------------------------------------------------------------------
-- OGRRE record metadata (audit trail — not well data)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS isgs.ogrre_record_metadata (
    report_name         TEXT PRIMARY KEY,       -- OGRRE record name (unique within OGRRE)
    mongo_id            TEXT,                   -- MongoDB _id of the source record
    source_processor    TEXT,                   -- OGRRE processor name (e.g. IL_Ver_A_WellCompletion)
    review_status       TEXT,                   -- reviewed | verified at time of sync
    reviewer            TEXT,                   -- email of last reviewer
    reviewed_at         TIMESTAMPTZ,            -- timestamp of last review update
    synced_at           TIMESTAMPTZ DEFAULT now()
);

-- ---------------------------------------------------------------------------
-- Completion Reports (main wide table)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS isgs.completion_reports (
    -- Identifiers & linkage
    id                              BIGSERIAL PRIMARY KEY,
    api_number                      TEXT,           -- 10-digit API (links to well_headers)
    sidetrack_id                    BIGINT,         -- 12-digit API (api_number || '00' for Illinois)
    report_name                     TEXT UNIQUE,    -- OGRRE record name, FK to ogrre_record_metadata
    synced_at                       TIMESTAMPTZ DEFAULT now(),

    -- Type of Report
    report_type_doph                BOOLEAN,        -- Drilled out of plugged hole
    report_type_conversion          BOOLEAN,
    report_type_deepening           BOOLEAN,
    report_type_workover            BOOLEAN,
    report_type_new_well            BOOLEAN,
    not_converted_permit_expired    BOOLEAN,
    not_drilled_permit_expired      BOOLEAN,
    lease_sign_no                   BOOLEAN,
    lease_sign_yes                  BOOLEAN,

    -- Well / Permit Identification
    well_name                       TEXT,
    operator                        TEXT,
    operator_number                 TEXT,
    county                          TEXT,
    field_name                      TEXT,
    permit_number                   TEXT,
    permit_date                     DATE,
    plss_loc                        TEXT,           -- PLSS location description
    section                         INTEGER,
    township                        TEXT,
    range                           TEXT,
    elev_df                         DOUBLE PRECISION,   -- Derrick floor elevation (ft)
    elev_kb                         DOUBLE PRECISION,   -- Kelly bushing elevation (ft)
    elev_ground                     DOUBLE PRECISION,   -- Ground elevation (ft)
    elev_gr                         DOUBLE PRECISION,   -- Ground elevation alt name (elev_gr)

    -- Well Type
    type_oil                        BOOLEAN,
    type_gas                        BOOLEAN,
    type_dry_hole                   BOOLEAN,
    type_swd                        BOOLEAN,        -- Salt water disposal
    type_water_input                BOOLEAN,
    type_gas_input                  BOOLEAN,
    type_water_inj                  BOOLEAN,        -- Water injection (alt name)
    type_gas_inj                    BOOLEAN,        -- Gas injection (alt name)
    type_conv                       BOOLEAN,        -- Conventional
    type_str_test                   BOOLEAN,        -- Stratigraphic test
    type_water_supply               BOOLEAN,
    type_observation                BOOLEAN,
    type_coal_bed_gas               BOOLEAN,
    type_coal_mine_gas              BOOLEAN,
    type_da                         BOOLEAN,        -- Dry and abandoned
    type_gas_storage                BOOLEAN,
    type_other                      BOOLEAN,
    type_other_text                 TEXT,
    type_service                    BOOLEAN,        -- Service well
    type_service_text               TEXT,
    well_type                       TEXT,           -- Free-text well type (WellCompletion_G)

    -- PLSS location subfields (WellCompletion_G)
    ns_distance                     DOUBLE PRECISION,   -- N-S footage from section line
    ns_line                         TEXT,               -- N or S
    ew_distance                     DOUBLE PRECISION,   -- E-W footage from section line
    ew_line                         TEXT,               -- E or W
    first_quarter                   TEXT,
    second_quarter                  TEXT,
    third_quarter                   TEXT,

    -- Well name variants (WellCompletion_G uses farm + well number)
    well_name_farm                  TEXT,
    well_name_number                TEXT,

    -- Misc metadata
    ref_number                      TEXT,           -- Reference number (Ver B)

    -- Depths & Drilling Dates
    total_depth                     DOUBLE PRECISION,   -- ft
    tvd                             DOUBLE PRECISION,   -- True vertical depth (ft)
    pbtd                            DOUBLE PRECISION,   -- Plug back total depth (ft)
    spud_date                       DATE,
    comp_date                       DATE,
    rotary_tools_from               DOUBLE PRECISION,   -- ft
    rotary_tools_to                 DOUBLE PRECISION,   -- ft
    cable_tools_from                DOUBLE PRECISION,   -- ft
    cable_tools_to                  DOUBLE PRECISION,   -- ft

    -- Wireline / Electric Logs
    logs_run_yes                    BOOLEAN,
    logs_run_no                     BOOLEAN,
    log_date                        DATE,           -- Date of most recent log
    log_type                        TEXT,           -- Type of most recent log

    -- DST & Coring
    dst_no                          BOOLEAN,
    dst_yes                         BOOLEAN,
    dst_zone                        TEXT,
    cored_no                        BOOLEAN,
    cored_yes                       BOOLEAN,
    cored_interval                  TEXT,           -- e.g. "4000-5000 ft"

    -- Surface Casing
    surf_cem_top                    DOUBLE PRECISION,   -- ft
    surf_cem_top_meth               TEXT,
    surf_cem_vol                    DOUBLE PRECISION,   -- sacks
    surf_csg_depth                  DOUBLE PRECISION,   -- ft
    surf_csg_pulled                 TEXT,
    surf_csg_out_diam               DOUBLE PRECISION,   -- inches
    surf_hole_size                  DOUBLE PRECISION,   -- inches

    -- Intermediate / Mine-String Casing
    int_cem_top                     DOUBLE PRECISION,   -- ft
    int_cem_top_meth                TEXT,
    int_cem_vol                     DOUBLE PRECISION,   -- sacks
    int_csg_depth                   DOUBLE PRECISION,   -- ft
    int_csg_pulled                  TEXT,
    int_csg_out_diam                DOUBLE PRECISION,   -- inches
    int_hole_size                   DOUBLE PRECISION,   -- inches

    -- Production Casing
    prod_cem_top                    DOUBLE PRECISION,   -- ft
    prod_cem_top_meth               TEXT,
    prod_cem_vol                    DOUBLE PRECISION,   -- sacks
    prod_csg_depth                  DOUBLE PRECISION,   -- ft
    prod_csg_pulled                 TEXT,
    prod_csg_out_diam               DOUBLE PRECISION,   -- inches
    prod_hole_size                  DOUBLE PRECISION,   -- inches

    -- Liner
    liner_cem_vol                   DOUBLE PRECISION,   -- sacks
    liner_depth                     DOUBLE PRECISION,   -- ft
    liner_pulled                    TEXT,
    liner_size                      DOUBLE PRECISION,   -- inches (OD)

    -- Tubing
    tubing_type                     TEXT,
    tubing_size                     DOUBLE PRECISION,   -- inches (OD)

    -- Other / Generic Casing (catches WellCompletion_G Casing_Record rows)
    oth_cem_top                     DOUBLE PRECISION,   -- ft
    oth_cem_vol                     DOUBLE PRECISION,   -- sacks
    oth_csg_depth                   DOUBLE PRECISION,   -- ft
    oth_csg_out_diam                DOUBLE PRECISION,   -- inches
    other_cem_top_meth              TEXT,
    other_hole_size                 DOUBLE PRECISION,   -- inches
    csg_depth                       DOUBLE PRECISION,   -- ft
    csg_out_diam                    DOUBLE PRECISION,   -- inches
    csg_type                        TEXT,
    cem_vol                         DOUBLE PRECISION,   -- sacks

    -- Packer
    packer_type                     TEXT,
    packer_depth                    DOUBLE PRECISION,   -- ft

    -- Completion / Production summary
    prod_inj_form                   TEXT,           -- Target formation
    lithology                       TEXT,
    first_prod_date                 DATE,
    test_date                       DATE,
    test_length                     TEXT,           -- e.g. "12 hours"
    post_test_prod                  TEXT,           -- e.g. "25 BBL"
    pre_test_prod                   TEXT,
    oil_prod                        DOUBLE PRECISION,   -- bbl/day
    gas_prod                        DOUBLE PRECISION,   -- mcf/day
    water_prod                      DOUBLE PRECISION,   -- bbl/day

    -- Perforations
    comp_form                       TEXT,
    perf_from                       DOUBLE PRECISION,   -- ft (shallowest)
    perf_to                         DOUBLE PRECISION,   -- ft (deepest)
    perf_int                        TEXT,           -- raw string e.g. "4500-5000"
    perf_shots                      TEXT,

    -- Completion Treatment
    treatment_acidized              BOOLEAN,
    treatment_acidized_fractures_other TEXT,
    treatment_amnt                  TEXT,
    treatment_date                  DATE,
    treatment_from                  DOUBLE PRECISION,   -- ft
    treatment_to                    DOUBLE PRECISION,   -- ft
    treatment_interval              TEXT,           -- raw string
    treatment_other                 BOOLEAN,
    treatment_perf                  BOOLEAN,
    treatment_shot                  BOOLEAN,
    treatment_fractured             BOOLEAN,
    open_hole_interval              TEXT,           -- raw string e.g. "4000-5000"
    open_hole_from                  DOUBLE PRECISION,   -- ft (parsed from open_hole_interval)
    open_hole_to                    DOUBLE PRECISION,   -- ft (parsed from open_hole_interval)

    -- Injection
    inj_form                        TEXT,
    inj_date                        DATE,
    inj_fluid_freshwater            BOOLEAN,
    inj_fluid_other                 BOOLEAN,
    inj_fluid_other_desc            TEXT,
    inj_fluid_saltwater             BOOLEAN,
    fluid_source                    TEXT,
    gas_inj_rate                    DOUBLE PRECISION,   -- MCF/day
    gas_press                       DOUBLE PRECISION,   -- psi
    water_inj_rate                  DOUBLE PRECISION,   -- bbl/day
    water_press                     DOUBLE PRECISION,   -- psi

    -- Signature / Submitter
    signature                       TEXT,
    signature_address               TEXT,
    signature_city_state            TEXT,
    signature_date                  DATE,
    signature_title                 TEXT,

    CONSTRAINT fk_completion_reports_metadata
        FOREIGN KEY (report_name) REFERENCES isgs.ogrre_record_metadata(report_name)
        ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_completion_reports_api
    ON isgs.completion_reports (api_number);
CREATE INDEX IF NOT EXISTS idx_completion_reports_sidetrack
    ON isgs.completion_reports (sidetrack_id);
CREATE INDEX IF NOT EXISTS idx_completion_reports_synced
    ON isgs.completion_reports (synced_at);
CREATE INDEX IF NOT EXISTS idx_completion_reports_county
    ON isgs.completion_reports (county);

-- ---------------------------------------------------------------------------
-- Child table: Wireline / Electric Logs (multiple logs per report)
-- Source: IL_Ver_B_Well_Completion :: Type_Of_Logs
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS isgs.completion_report_logs (
    id                      SERIAL PRIMARY KEY,
    completion_report_id    BIGINT NOT NULL REFERENCES isgs.completion_reports(id) ON DELETE CASCADE,
    occurrence_idx          INTEGER NOT NULL,   -- row order (0-based)
    log_type                TEXT,
    log_date                DATE
);
CREATE INDEX IF NOT EXISTS idx_cr_logs_report
    ON isgs.completion_report_logs (completion_report_id);

-- ---------------------------------------------------------------------------
-- Child table: Completion Intervals (multiple intervals per report)
-- Source: IL_Ver_B_Well_Completion :: Completion_For_Production
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS isgs.completion_report_completion_intervals (
    id                              SERIAL PRIMARY KEY,
    completion_report_id            BIGINT NOT NULL REFERENCES isgs.completion_reports(id) ON DELETE CASCADE,
    occurrence_idx                  INTEGER NOT NULL,
    comp_form                       TEXT,           -- Formation_Name
    lithology                       TEXT,
    perforation_interval            TEXT,           -- raw string
    perf_int                        TEXT,           -- alias for perforation_interval
    perf_from                       DOUBLE PRECISION,
    perf_to                         DOUBLE PRECISION,
    perf_shots                      TEXT,
    open_hole_interval              TEXT,
    open_hole_from                  DOUBLE PRECISION,
    open_hole_to                    DOUBLE PRECISION,
    treatment_acidized_fractures_other TEXT
);
CREATE INDEX IF NOT EXISTS idx_cr_completion_intervals_report
    ON isgs.completion_report_completion_intervals (completion_report_id);

-- ---------------------------------------------------------------------------
-- Child table: Gun Perforating Windows
-- Source: IL_WellCompletion_G :: Gun_Perforating_Windows
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS isgs.completion_report_gun_perforating_windows (
    id                      SERIAL PRIMARY KEY,
    completion_report_id    BIGINT NOT NULL REFERENCES isgs.completion_reports(id) ON DELETE CASCADE,
    occurrence_idx          INTEGER NOT NULL,
    no_shots                INTEGER,
    perf_shots              TEXT,               -- no_shots as text (alias)
    perf_from               DOUBLE PRECISION,
    perf_to                 DOUBLE PRECISION
);
CREATE INDEX IF NOT EXISTS idx_cr_gpw_report
    ON isgs.completion_report_gun_perforating_windows (completion_report_id);

-- ---------------------------------------------------------------------------
-- Child table: Acid / Shooting / Fracture Treatment Records
-- Source: IL_WellCompletion_G :: Acid_Or_Shooting_Record_Or_Fracture_Treatment
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS isgs.completion_report_acid_records (
    id                      SERIAL PRIMARY KEY,
    completion_report_id    BIGINT NOT NULL REFERENCES isgs.completion_reports(id) ON DELETE CASCADE,
    occurrence_idx          INTEGER NOT NULL,
    treatment_date          DATE,
    treatment_from          DOUBLE PRECISION,   -- ft
    treatment_to            DOUBLE PRECISION,   -- ft
    treatment_amnt          TEXT
);
CREATE INDEX IF NOT EXISTS idx_cr_acid_records_report
    ON isgs.completion_report_acid_records (completion_report_id);

-- ---------------------------------------------------------------------------
-- Child table: Casing Records (generic, from WellCompletion_G Casing_Record)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS isgs.completion_report_casing_records (
    id                      SERIAL PRIMARY KEY,
    completion_report_id    BIGINT NOT NULL REFERENCES isgs.completion_reports(id) ON DELETE CASCADE,
    occurrence_idx          INTEGER NOT NULL,
    csg_size                DOUBLE PRECISION,   -- inches (OD) — alt col
    csg_out_diam            DOUBLE PRECISION,   -- inches (OD) — mapped name from YAML
    csg_depth               DOUBLE PRECISION,   -- ft
    cem_vol                 DOUBLE PRECISION,   -- sacks (mapped name from YAML)
    cement_sacks            DOUBLE PRECISION    -- sacks (alt col)
);

-- ---------------------------------------------------------------------------
-- Child table: Packers (from IL_Ver_B_Well_Completion :: Packer)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS isgs.completion_report_packers (
    id                      SERIAL PRIMARY KEY,
    completion_report_id    BIGINT NOT NULL REFERENCES isgs.completion_reports(id) ON DELETE CASCADE,
    occurrence_idx          INTEGER NOT NULL,
    packer_type             TEXT,
    packer_depth            DOUBLE PRECISION
);
CREATE INDEX IF NOT EXISTS idx_cr_casing_records_report
    ON isgs.completion_report_casing_records (completion_report_id);

-- ---------------------------------------------------------------------------
-- Sync audit log
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS isgs.sync_log (
    id              SERIAL PRIMARY KEY,
    started_at      TIMESTAMPTZ NOT NULL,
    finished_at     TIMESTAMPTZ,
    collaborator    TEXT,                   -- 'isgs' | 'calgem' | 'osage'
    form_type       TEXT,                   -- 'completion_reports' | 'plugging_reports' | ...
    records_synced  INTEGER DEFAULT 0,
    records_failed  INTEGER DEFAULT 0,
    error_message   TEXT,
    status          TEXT                    -- 'running' | 'success' | 'failed'
);
