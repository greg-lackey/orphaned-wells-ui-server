"""
synthesizer.py — Populates Layer 2 (well-state) tables from Layer 1 (completion_reports).

Reads entirely from PostgreSQL Layer 1 — does not re-read MongoDB.
Each function is idempotent and safe to re-run.
"""
import logging

import psycopg2

log = logging.getLogger(__name__)


def run_synthesis(conn, schema: str = "isgs") -> None:
    """Run all Layer 2 synthesis functions in dependency order."""
    log.info("Starting Layer 2 synthesis (schema=%s)", schema)
    synthesize_sidetracks(conn, schema)
    synthesize_casings(conn, schema)
    synthesize_logs(conn, schema)
    synthesize_completions(conn, schema)
    synthesize_production(conn, schema)
    synthesize_injection(conn, schema)
    log.info("Layer 2 synthesis complete")


def synthesize_sidetracks(conn, schema: str = "isgs") -> int:
    """
    Upsert isgs.sidetracks using latest-wins logic.
    The WHERE clause on DO UPDATE ensures an older report never overwrites a newer one.
    Returns the number of rows affected.
    """
    sql = f"""
        INSERT INTO {schema}.sidetracks (
            id, well_id, type, permit_number, permit_date, spud_date, comp_date,
            tvd, pbtd,
            rotary_tools_from, rotary_tools_to, cable_tools_from, cable_tools_to,
            logs_run, cored, dst, dst_zone,
            not_converted_permit_expired, not_drilled_permit_expired,
            source_report_name, source_report_date, last_synthesized_at
        )
        SELECT DISTINCT ON (sidetrack_id)
            sidetrack_id,
            CAST(api_number AS BIGINT),
            CASE
                WHEN type_oil      THEN 'Oil'
                WHEN type_gas      THEN 'Gas'
                WHEN type_dry_hole THEN 'Dry Hole'
                WHEN type_swd      THEN 'SWD'
                ELSE well_type
            END,
            permit_number,
            permit_date,
            spud_date,
            comp_date,
            COALESCE(tvd, total_depth),
            pbtd,
            rotary_tools_from, rotary_tools_to,
            cable_tools_from,  cable_tools_to,
            COALESCE(logs_run_yes, NOT logs_run_no),
            COALESCE(cored_yes,    NOT cored_no),
            COALESCE(dst_yes,      NOT dst_no),
            dst_zone,
            not_converted_permit_expired,
            not_drilled_permit_expired,
            report_name,
            COALESCE(comp_date, permit_date),
            now()
        FROM {schema}.completion_reports
        WHERE sidetrack_id IS NOT NULL
          AND api_number ~ '^[0-9]+$'
        ORDER BY sidetrack_id,
                 COALESCE(comp_date, permit_date, synced_at::date) DESC NULLS LAST
        ON CONFLICT (id) DO UPDATE SET
            type                        = COALESCE(EXCLUDED.type,                        {schema}.sidetracks.type),
            permit_number               = COALESCE(EXCLUDED.permit_number,               {schema}.sidetracks.permit_number),
            permit_date                 = COALESCE(EXCLUDED.permit_date,                 {schema}.sidetracks.permit_date),
            spud_date                   = COALESCE(EXCLUDED.spud_date,                   {schema}.sidetracks.spud_date),
            comp_date                   = COALESCE(EXCLUDED.comp_date,                   {schema}.sidetracks.comp_date),
            tvd                         = COALESCE(EXCLUDED.tvd,                         {schema}.sidetracks.tvd),
            pbtd                        = COALESCE(EXCLUDED.pbtd,                        {schema}.sidetracks.pbtd),
            rotary_tools_from           = COALESCE(EXCLUDED.rotary_tools_from,           {schema}.sidetracks.rotary_tools_from),
            rotary_tools_to             = COALESCE(EXCLUDED.rotary_tools_to,             {schema}.sidetracks.rotary_tools_to),
            cable_tools_from            = COALESCE(EXCLUDED.cable_tools_from,            {schema}.sidetracks.cable_tools_from),
            cable_tools_to              = COALESCE(EXCLUDED.cable_tools_to,              {schema}.sidetracks.cable_tools_to),
            logs_run                    = COALESCE(EXCLUDED.logs_run,                    {schema}.sidetracks.logs_run),
            cored                       = COALESCE(EXCLUDED.cored,                       {schema}.sidetracks.cored),
            dst                         = COALESCE(EXCLUDED.dst,                         {schema}.sidetracks.dst),
            dst_zone                    = COALESCE(EXCLUDED.dst_zone,                    {schema}.sidetracks.dst_zone),
            not_converted_permit_expired = COALESCE(EXCLUDED.not_converted_permit_expired, {schema}.sidetracks.not_converted_permit_expired),
            not_drilled_permit_expired  = COALESCE(EXCLUDED.not_drilled_permit_expired,  {schema}.sidetracks.not_drilled_permit_expired),
            source_report_name          = EXCLUDED.source_report_name,
            source_report_date          = EXCLUDED.source_report_date,
            last_synthesized_at         = now()
        WHERE EXCLUDED.source_report_date >= {schema}.sidetracks.source_report_date
           OR {schema}.sidetracks.source_report_date IS NULL
    """
    with conn:
        with conn.cursor() as cur:
            cur.execute(sql)
            count = cur.rowcount
    log.info("synthesize_sidetracks: %d rows affected", count)
    return count


def synthesize_casings(conn, schema: str = "isgs") -> int:
    """
    Unpivot flat casing columns from completion_reports into isgs.casings.
    One row per (sidetrack_id, casing_type). Latest report wins per pair.
    """
    sql = f"""
        WITH casing_candidates AS (
            SELECT sidetrack_id, 'surface' AS type, report_name,
                   COALESCE(comp_date, permit_date) AS report_date,
                   surf_hole_size      AS hole_size,
                   surf_csg_out_diam   AS out_diam,
                   surf_cem_vol        AS cem_vol,
                   surf_csg_depth      AS tvd,
                   surf_csg_pulled     AS pulled,
                   surf_cem_top        AS cem_top_md,
                   surf_cem_top_meth   AS cem_top_method
            FROM {schema}.completion_reports
            WHERE sidetrack_id IS NOT NULL
              AND (surf_csg_depth IS NOT NULL OR surf_csg_out_diam IS NOT NULL)

            UNION ALL

            SELECT sidetrack_id, 'intermediate', report_name,
                   COALESCE(comp_date, permit_date),
                   int_hole_size,
                   int_csg_out_diam,
                   int_cem_vol,
                   int_csg_depth,
                   int_csg_pulled,
                   int_cem_top,
                   int_cem_top_meth
            FROM {schema}.completion_reports
            WHERE sidetrack_id IS NOT NULL
              AND (int_csg_depth IS NOT NULL OR int_csg_out_diam IS NOT NULL)

            UNION ALL

            SELECT sidetrack_id, 'production', report_name,
                   COALESCE(comp_date, permit_date),
                   prod_hole_size,
                   prod_csg_out_diam,
                   prod_cem_vol,
                   prod_csg_depth,
                   prod_csg_pulled,
                   prod_cem_top,
                   prod_cem_top_meth
            FROM {schema}.completion_reports
            WHERE sidetrack_id IS NOT NULL
              AND (prod_csg_depth IS NOT NULL OR prod_csg_out_diam IS NOT NULL)

            UNION ALL

            SELECT sidetrack_id, 'liner', report_name,
                   COALESCE(comp_date, permit_date),
                   NULL,
                   liner_size,
                   liner_cem_vol,
                   liner_depth,
                   liner_pulled,
                   NULL,
                   NULL
            FROM {schema}.completion_reports
            WHERE sidetrack_id IS NOT NULL
              AND (liner_depth IS NOT NULL OR liner_size IS NOT NULL)

            UNION ALL

            SELECT sidetrack_id, 'other', report_name,
                   COALESCE(comp_date, permit_date),
                   other_hole_size,
                   oth_csg_out_diam,
                   oth_cem_vol,
                   oth_csg_depth,
                   NULL,
                   oth_cem_top,
                   other_cem_top_meth
            FROM {schema}.completion_reports
            WHERE sidetrack_id IS NOT NULL
              AND (oth_csg_depth IS NOT NULL OR oth_csg_out_diam IS NOT NULL)
        ),
        ranked AS (
            SELECT *,
                   ROW_NUMBER() OVER (
                       PARTITION BY sidetrack_id, type
                       ORDER BY report_date DESC NULLS LAST
                   ) AS rn
            FROM casing_candidates
        )
        INSERT INTO {schema}.casings (
            sidetrack_id, type, hole_size, out_diam, cem_vol,
            tvd, pulled, cem_top_md, cem_top_method, source_report_name,
            last_synthesized_at
        )
        SELECT sidetrack_id, type, hole_size, out_diam, cem_vol,
               tvd, pulled, cem_top_md, cem_top_method, report_name,
               now()
        FROM ranked
        WHERE rn = 1
        ON CONFLICT (sidetrack_id, type) DO UPDATE SET
            hole_size           = COALESCE(EXCLUDED.hole_size,       {schema}.casings.hole_size),
            out_diam            = COALESCE(EXCLUDED.out_diam,        {schema}.casings.out_diam),
            cem_vol             = COALESCE(EXCLUDED.cem_vol,         {schema}.casings.cem_vol),
            tvd                 = COALESCE(EXCLUDED.tvd,             {schema}.casings.tvd),
            pulled              = COALESCE(EXCLUDED.pulled,          {schema}.casings.pulled),
            cem_top_md          = COALESCE(EXCLUDED.cem_top_md,      {schema}.casings.cem_top_md),
            cem_top_method      = COALESCE(EXCLUDED.cem_top_method,  {schema}.casings.cem_top_method),
            source_report_name  = EXCLUDED.source_report_name,
            last_synthesized_at = now()
    """
    with conn:
        with conn.cursor() as cur:
            cur.execute(sql)
            count = cur.rowcount
    log.info("synthesize_casings: %d rows affected", count)
    return count


def synthesize_logs(conn, schema: str = "isgs") -> int:
    """
    Append log runs to isgs.logs. Sources both the child table and flat columns.
    ON CONFLICT DO NOTHING makes this idempotent.
    """
    sql = f"""
        INSERT INTO {schema}.logs (sidetrack_id, log_type, log_date, source_report_name)

        -- From the child table (multi-row log entries)
        SELECT cr.sidetrack_id, crl.log_type, crl.log_date, cr.report_name
        FROM {schema}.completion_report_logs crl
        JOIN {schema}.completion_reports cr ON cr.id = crl.completion_report_id
        WHERE cr.sidetrack_id IS NOT NULL
          AND crl.log_date IS NOT NULL

        UNION

        -- From flat columns on the main table
        SELECT sidetrack_id, log_type, log_date, report_name
        FROM {schema}.completion_reports
        WHERE sidetrack_id IS NOT NULL
          AND log_date IS NOT NULL

        ON CONFLICT (sidetrack_id, log_date, log_type) DO NOTHING
    """
    with conn:
        with conn.cursor() as cur:
            cur.execute(sql)
            count = cur.rowcount
    log.info("synthesize_logs: %d rows affected", count)
    return count


def synthesize_completions(conn, schema: str = "isgs") -> int:
    """
    Append completion intervals to isgs.completions.
    Sources both the child table (IL_Ver_B multi-row) and flat columns (IL_Ver_A, IL_WellCompletion_G).
    """
    sql = f"""
        INSERT INTO {schema}.completions (
            sidetrack_id, source_report_name, form, lithology,
            open_hole_from, open_hole_to,
            perf_from, perf_to, perf_shots,
            treatment_from, treatment_to, treatment_amnt, treatment_date
        )

        -- From child table (multi-row completions per report)
        SELECT cr.sidetrack_id, cr.report_name,
               ci.comp_form, ci.lithology,
               ci.open_hole_from, ci.open_hole_to,
               ci.perf_from, ci.perf_to, ci.perf_shots,
               NULL, NULL, NULL, NULL
        FROM {schema}.completion_report_completion_intervals ci
        JOIN {schema}.completion_reports cr ON cr.id = ci.completion_report_id
        WHERE cr.sidetrack_id IS NOT NULL

        UNION

        -- From flat columns (single completion per report)
        SELECT sidetrack_id, report_name,
               comp_form, lithology,
               open_hole_from, open_hole_to,
               perf_from, perf_to, perf_shots,
               treatment_from, treatment_to, treatment_amnt, treatment_date
        FROM {schema}.completion_reports
        WHERE sidetrack_id IS NOT NULL
          AND (comp_form IS NOT NULL OR perf_from IS NOT NULL OR open_hole_from IS NOT NULL)

        ON CONFLICT (sidetrack_id, source_report_name) DO NOTHING
    """
    with conn:
        with conn.cursor() as cur:
            cur.execute(sql)
            count = cur.rowcount
    log.info("synthesize_completions: %d rows affected", count)
    return count


def synthesize_production(conn, schema: str = "isgs") -> int:
    """
    Append production test results to isgs.production_testing.
    """
    sql = f"""
        INSERT INTO {schema}.production_testing (
            sidetrack_id, source_report_name, form,
            test_date, test_length, pre_test_prod, post_test_prod,
            gas_prod, oil_prod, water_prod
        )
        SELECT
            sidetrack_id,
            report_name,
            prod_inj_form,
            test_date,
            test_length,
            pre_test_prod,
            post_test_prod,
            gas_prod,
            oil_prod,
            water_prod
        FROM {schema}.completion_reports
        WHERE sidetrack_id IS NOT NULL
          AND (oil_prod IS NOT NULL OR gas_prod IS NOT NULL OR water_prod IS NOT NULL
               OR test_date IS NOT NULL)
        ON CONFLICT (sidetrack_id, source_report_name) DO NOTHING
    """
    with conn:
        with conn.cursor() as cur:
            cur.execute(sql)
            count = cur.rowcount
    log.info("synthesize_production: %d rows affected", count)
    return count


def synthesize_injection(conn, schema: str = "isgs") -> int:
    """
    Append injection test results to isgs.injection_testing.
    """
    sql = f"""
        INSERT INTO {schema}.injection_testing (
            sidetrack_id, source_report_name,
            fluid_source, form, inj_date,
            fluid_type,
            water_inj_rate, water_psi,
            gas_inj_rate, gas_press
        )
        SELECT
            sidetrack_id,
            report_name,
            fluid_source,
            inj_form,
            inj_date,
            CASE
                WHEN inj_fluid_freshwater THEN 'freshwater'
                WHEN inj_fluid_saltwater  THEN 'saltwater'
                WHEN inj_fluid_other      THEN inj_fluid_other_desc
            END,
            water_inj_rate,
            water_press,
            gas_inj_rate,
            gas_press
        FROM {schema}.completion_reports
        WHERE sidetrack_id IS NOT NULL
          AND (water_inj_rate IS NOT NULL OR gas_inj_rate IS NOT NULL OR inj_date IS NOT NULL)
        ON CONFLICT (sidetrack_id, source_report_name) DO NOTHING
    """
    with conn:
        with conn.cursor() as cur:
            cur.execute(sql)
            count = cur.rowcount
    log.info("synthesize_injection: %d rows affected", count)
    return count
