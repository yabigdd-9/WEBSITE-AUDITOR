plan:
  name: "WEBSITE-AUDITOR Data Gap + Big Data Intelligence Master Plan"
  version: "1.0.0"
  date: "2026-09-23"
  status: "READY_FOR_IMPLEMENTATION"

  repository:
    name: "WEBSITE-AUDITOR"
    canonical_workspace: "/Users/dd/WEBSITE-AUDITOR"
    reviewed_branch: "integration/v41-release-candidate"

  mission: >
    Upgrade WEBSITE-AUDITOR from a strong deterministic website-auditing
    engine into a large-scale NZ business and web-intelligence platform
    capable of discovering, identifying, enriching, auditing, scoring,
    monitoring, and learning from businesses while preserving raw evidence,
    provenance, source licensing, confidence, and human-review boundaries.

  primary_finding: >
    The repository does not primarily need another large dump of random
    prospect records. It needs a normalized enrichment and provenance layer
    capable of accepting high-value large datasets without discarding useful
    fields or confusing business identity, website identity, observation,
    market context, and audit evidence.

  guiding_principles:
    - "Evidence first."
    - "Preserve source values."
    - "Never overwrite contradictory source observations."
    - "Separate business identity from website observations."
    - "Separate technical audit score from commercial opportunity score."
    - "Use authoritative sources when available."
    - "Prefer free/open/permissively licensed sources."
    - "Local-first processing where practical."
    - "All bulk ingestion must retain provenance."
    - "No guessed identifiers become verified identifiers."
    - "No inferred vulnerabilities become confirmed vulnerabilities."
    - "No outreach eligibility is granted merely because contact data exists."
    - "Human approval remains required for high-risk external actions."
    - "Paid API fallback remains disabled unless explicitly approved."

current_repository_state:

  audit_engine:
    status: "STRONG"
    already_present:
      - "HTML and page analysis"
      - "SEO basics"
      - "JSON-LD/schema inspection"
      - "HTTP response inspection"
      - "security headers"
      - "cookie inspection"
      - "robots.txt analysis"
      - "sitemap analysis"
      - "mixed-content detection"
      - "conversion signal detection"
      - "internal-link discovery"
      - "broken-link validation"
      - "DNS inspection"
      - "TLS inspection"
      - "bounded crawler"
      - "browser/rendered checks"
      - "accessibility browser lane"
      - "Lighthouse integration"
      - "Lychee integration"
      - "evidence records"
      - "deterministic findings"
      - "remediation previews"
      - "demo generation"
      - "deterministic quote engine"

  discovery:
    status: "PARTIALLY_IMPLEMENTED"
    existing_sources:
      - "local CSV"
      - "local JSON"
      - "local JSONL"
      - "NZBN-style imports"
      - "OSM-style imports"
      - "self-hosted loopback SearXNG"
    existing_normalized_fields:
      - "name"
      - "normalized_name"
      - "legal_name"
      - "trading_name"
      - "region"
      - "public_website"
      - "canonical_host"
      - "source"
      - "source provenance"
    problem: >
      Rich source records are reduced to a relatively small candidate model.
      This is sufficient for prospect discovery but insufficient for building
      a long-lived business intelligence database.

  identity_resolution:
    status: "IMPLEMENTED_BUT_NEEDS_DATA_EXPANSION"
    current_signals:
      - "NZBN"
      - "legal name"
      - "trading name"
      - "domain"
      - "website"
      - "email domain"
      - "region"
      - "address"
      - "phone"
    target: >
      Expand identity evidence rather than simply increasing fuzzy matching.

  performance_data:
    current:
      - "Lighthouse laboratory data"
      - "browser observations"
    missing:
      - "real-user Core Web Vitals"
      - "historical real-user performance"

  market_data:
    status: "MAJOR_GAP"
    current: "Mostly internal scoring and manually defined assumptions."
    missing:
      - "authoritative NZ industry baselines"
      - "regional business density"
      - "industry business counts"
      - "business births/deaths"
      - "employment context"
      - "market saturation indicators"

  historic_web_data:
    status: "MAJOR_GAP"
    missing:
      - "historic website snapshots"
      - "historic content observations"
      - "historic site-change signals"
      - "technology change history"
      - "domain lifecycle history"

data_priority_matrix:

  P0:

    companies_office_bulk:
      priority: "CRITICAL"
      type: "AUTHORITATIVE_NZ_BUSINESS_IDENTITY"
      purpose:
        - "business identity"
        - "company verification"
        - "industry classification"
        - "status verification"
        - "address enrichment"
      desired_fields:
        - "NZBN"
        - "company number"
        - "legal name"
        - "entity status"
        - "entity type"
        - "registration date"
        - "removal date"
        - "BIC industry classification"
        - "registered addresses"
        - "directorship relationships where appropriate"
        - "shareholder relationships where appropriate"
        - "insolvency-related public information where applicable"
      implementation:
        frequency: "monthly bulk snapshot"
        strategy: "incremental ingest with source version tracking"
      value: "VERY_HIGH"

    nzbn_api:
      priority: "CRITICAL"
      type: "AUTHORITATIVE_NZ_ENTITY_ENRICHMENT"
      purpose:
        - "verify company/business identity"
        - "refresh current business data"
        - "observe authoritative changes"
      desired_fields:
        - "NZBN"
        - "legal name"
        - "trading names"
        - "entity type"
        - "business status"
        - "public addresses"
        - "public contact details when supplied"
      implementation:
        mode: "API enrichment and change checking"
        bulk_role: "Companies Office remains better for bulk baseline ingestion"
      value: "VERY_HIGH"

    overture_maps_places:
      priority: "CRITICAL"
      type: "LARGE_SCALE_DISCOVERY_AND_ENRICHMENT"
      purpose:
        - "bulk business discovery"
        - "POI enrichment"
        - "location intelligence"
        - "business website discovery"
        - "phone/social enrichment"
      desired_fields:
        - "Overture/GERS place ID"
        - "geometry"
        - "names"
        - "addresses"
        - "basic category"
        - "taxonomy categories"
        - "operating status"
        - "websites"
        - "phones"
        - "emails when present"
        - "social accounts"
        - "brand"
        - "confidence"
        - "source metadata"
      query_strategy:
        engine: "DuckDB"
        format: "GeoParquet"
        initial_filter:
          country: "NZ"
      notes:
        - "Do not ingest the entire global places dataset into SQLite."
        - "Filter to New Zealand and selected categories/regions first."
        - "Preserve Overture source IDs and confidence."
      value: "VERY_HIGH"

    public_suffix_list:
      priority: "CRITICAL"
      type: "DOMAIN_NORMALIZATION"
      purpose:
        - "determine organizational registrable domain"
        - "improve deduplication"
        - "improve website-to-business matching"
        - "avoid treating subdomains as separate companies"
      examples:
        - "www.example.co.nz -> example.co.nz"
        - "booking.example.co.nz -> example.co.nz"
        - "mail.example.co.nz -> example.co.nz"
      required_change:
        - "replace simple www stripping with PSL-aware registrable-domain logic"
      value: "VERY_HIGH"

    crux:
      priority: "CRITICAL"
      type: "REAL_USER_WEB_PERFORMANCE"
      purpose:
        - "real field Core Web Vitals"
        - "validate Lighthouse findings"
        - "provide historical performance evidence"
      desired_metrics:
        - "LCP"
        - "INP"
        - "CLS"
        - "FCP"
        - "TTFB"
      important_distinction:
        lighthouse: "laboratory observation"
        crux: "aggregated real-user field observation"
      behavior:
        - "CrUX absence is not a website defect."
        - "Low-traffic NZ businesses may not have field data."
      value: "VERY_HIGH"

    stats_nz_business_demography:
      priority: "CRITICAL"
      type: "MARKET_CONTEXT"
      purpose:
        - "industry benchmarking"
        - "regional opportunity scoring"
        - "market density"
        - "industry trends"
      desired_metrics:
        - "business counts"
        - "business births"
        - "business deaths"
        - "industry classification"
        - "region"
        - "employment indicators"
      use:
        - "commercial opportunity scoring"
        - "industry prioritization"
        - "regional market sizing"
      rule: >
        Stats NZ market data must never modify technical website audit severity.
        It belongs in a separate commercial/market context score.
      value: "VERY_HIGH"

  P1:

    linz:
      priority: "HIGH"
      type: "LOCATION_AND_ADDRESS_NORMALIZATION"
      purpose:
        - "normalize NZ addresses"
        - "resolve suburb/locality/region"
        - "geocode business locations"
        - "distinguish branches"
      desired_fields:
        - "street address identifier"
        - "street"
        - "suburb"
        - "locality"
        - "territorial authority"
        - "region"
        - "latitude"
        - "longitude"
      value: "HIGH"

    common_crawl:
      priority: "HIGH"
      type: "HISTORICAL_WEB_INTELLIGENCE"
      purpose:
        - "historic website discovery"
        - "content-history reconstruction"
        - "abandoned-site detection"
        - "previous phone/address detection"
        - "technology history"
        - "website age/activity signals"
      use_cases:
        - "determine whether website has materially changed"
        - "detect long-term abandoned websites"
        - "detect previously available booking functionality"
        - "identify redesign/replatform events"
        - "compare old and current contact information"
      recommended_access:
        - "Common Crawl index"
        - "Parquet index"
        - "DuckDB"
      notes:
        - "Do not download petabytes of crawl content."
        - "Query known NZ domains selectively."
      value: "HIGH"

    osv:
      priority: "HIGH"
      type: "VULNERABILITY_INTELLIGENCE"
      purpose:
        - "map confirmed software/version fingerprints to known vulnerabilities"
      integration_dependency:
        - "technology/version detection"
      rules:
        - "Technology detection alone does not prove version."
        - "Version inference must carry confidence."
        - "Only version-supported matches become vulnerability candidates."
      value: "HIGH"

    cisa_kev:
      priority: "HIGH"
      type: "EXPLOITED_VULNERABILITY_CONTEXT"
      purpose:
        - "flag known exploited vulnerabilities"
      relationship:
        osv: "broad vulnerability database"
        cisa_kev: "subset with evidence of exploitation in the wild"
      rule: >
        KEV presence raises context/urgency only after a vulnerability mapping is
        supported by sufficiently strong technology/version evidence.
      value: "HIGH"

    rdap:
      priority: "HIGH"
      type: "DOMAIN_LIFECYCLE_INTELLIGENCE"
      purpose:
        - "domain creation/registration context"
        - "domain status"
        - "expiration/lifecycle observations where available"
        - "registrar context"
      repository_state:
        legacy_implementation: true
        canonical_pipeline: false
      action:
        - "promote a bounded RDAP adapter into the canonical enrichment pipeline"
      constraints:
        - "respect registry/ICANN usage requirements"
        - "do not use as a mass marketing-contact harvesting mechanism"
      value: "HIGH"

    osm:
      priority: "HIGH"
      type: "LOCAL_BUSINESS_AND_PLACE_COMPLEMENT"
      purpose:
        - "complement Overture"
        - "fill local POI/location gaps"
        - "supply branch/location details"
      repository_state:
        import_adapter: true
        acquisition_pipeline: "operator-configured"
      recommendation:
        bulk: "regional extracts/self-hosted workflows"
        live_queries: "rate-limited and respectful"
      value: "HIGH"

  P2:

    http_archive:
      priority: "MEDIUM"
      type: "WEB_BENCHMARKING"
      purpose:
        - "web technology benchmark data"
        - "performance benchmark data"
        - "industry-wide web trends"
      best_use:
        - "contextual comparisons"
        - "research"
        - "benchmark dashboards"
      not_for:
        - "primary business discovery"
      value: "MEDIUM"

    charities_register:
      priority: "MEDIUM"
      type: "VERTICAL_DATASET"
      purpose:
        - "charity/entity enrichment"
        - "sector research"
        - "location/activity/financial context"
      restriction:
        - "Do not harvest published charity emails for marketing."
      outreach_eligibility_source: false
      value: "MEDIUM"

  P3:

    nz_zone_file:
      priority: "LOW_DEFERRED"
      type: "DOMAIN_UNIVERSE"
      purpose:
        - "potential .nz domain discovery"
      constraint: >
        Access is not intended to be treated as an unrestricted commercial
        prospecting feed. Approval/public-good requirements make it unsuitable
        as a core dependency for the current system.
      recommendation: "DEFER"
      value: "SPECIAL_CASE"

datasets_and_services_to_avoid_or_restrict:

  google_places:
    default_status: "REJECT_FOR_ZERO_COST_CORE"
    reason:
      - "billing/card requirement"
      - "conflicts with zero-paid-cost target"
    allowed_future_state: "explicitly approved paid integration only"

  google_safe_browsing:
    default_status: "DO_NOT_USE_FOR_COMMERCIAL_CORE"
    reason:
      - "free API has non-commercial usage constraints"
    commercial_alternative: "Google Web Risk"
    current_plan: "do not integrate"

  public_nominatim_high_volume:
    status: "RESTRICT"
    reason:
      - "public-instance usage restrictions"
      - "unsuitable for continuous bulk commercial pipeline"
    preferred:
      - "LINZ data"
      - "Overture"
      - "regional OSM extracts"
      - "self-hosting if eventually justified"

  public_overpass_high_volume:
    status: "RESTRICT"
    use_for:
      - "development"
      - "testing"
      - "small bounded queries"
    avoid_for:
      - "continuous high-volume prospect harvesting"
    preferred:
      - "Overture bulk"
      - "OSM extracts"
      - "self-hosted Overpass if later needed"

  charities_register_email:
    status: "PROHIBIT_FOR_MARKETING_HARVEST"
    use_for:
      - "entity research"
      - "sector analytics"
    outreach_eligibility_source: false

core_data_model_redesign:

  principle: >
    Do not turn the existing businesses table into a 50-column dumping ground.
    Keep businesses as the canonical entity and add normalized enrichment and
    observation tables.

  keep_business_table_small:
    suggested_fields:
      - "id"
      - "canonical_display_name"
      - "primary_website_id"
      - "industry_id"
      - "status"
      - "created_at"
      - "updated_at"

  new_tables:

    business_identifiers:
      purpose: "authoritative and external identifiers"
      fields:
        - "id"
        - "business_id"
        - "identifier_type"
        - "identifier_value"
        - "source"
        - "source_record_id"
        - "confidence"
        - "observed_at"
        - "expires_at"
      identifier_types:
        - "NZBN"
        - "COMPANIES_OFFICE_NUMBER"
        - "OVERTURE_PLACE_ID"
        - "OSM_ID"
        - "CHARITY_ID"

    business_names:
      purpose: "preserve legal/trading/alternate names independently"
      fields:
        - "business_id"
        - "name"
        - "name_type"
        - "source"
        - "source_record_id"
        - "observed_at"
        - "confidence"
      name_types:
        - "LEGAL"
        - "TRADING"
        - "DISPLAY"
        - "HISTORICAL"
        - "ALIAS"

    business_locations:
      purpose: "normalized business/branch/service-area geography"
      fields:
        - "business_id"
        - "location_type"
        - "raw_address"
        - "normalized_address"
        - "suburb"
        - "city"
        - "territorial_authority"
        - "region"
        - "postcode"
        - "latitude"
        - "longitude"
        - "linz_identifier"
        - "source"
        - "observed_at"
        - "confidence"

    business_classifications:
      purpose: "industry/category taxonomy"
      fields:
        - "business_id"
        - "classification_system"
        - "classification_code"
        - "classification_label"
        - "source"
        - "observed_at"
        - "confidence"
      systems:
        - "BIC"
        - "OVERTURE_TAXONOMY"
        - "OSM_TAG"
        - "INTERNAL_VERTICAL"

    business_sources:
      purpose: "source-level provenance"
      fields:
        - "business_id"
        - "source_name"
        - "source_record_id"
        - "source_url"
        - "source_version"
        - "retrieved_at"
        - "license"
        - "raw_sha256"
        - "ingestion_run_id"

    website_entities:
      purpose: "separate website/domain identity from business identity"
      fields:
        - "id"
        - "business_id"
        - "url"
        - "hostname"
        - "registrable_domain"
        - "scheme"
        - "relationship"
        - "first_seen"
        - "last_seen"
        - "confidence"
      relationship_types:
        - "PRIMARY"
        - "BRANCH"
        - "BOOKING"
        - "ECOMMERCE"
        - "LEGACY"
        - "UNCONFIRMED"

    website_observations:
      purpose: "timestamped website facts"
      fields:
        - "website_id"
        - "observation_type"
        - "value_json"
        - "observed_at"
        - "source"
        - "confidence"
        - "capture_hash"

    technology_observations:
      purpose: "technology fingerprint history"
      fields:
        - "website_id"
        - "technology"
        - "version"
        - "version_confidence"
        - "evidence"
        - "observed_at"
        - "detector_version"

    field_performance:
      purpose: "CrUX and other field measurements"
      fields:
        - "website_id"
        - "source"
        - "scope"
        - "period_start"
        - "period_end"
        - "lcp"
        - "inp"
        - "cls"
        - "fcp"
        - "ttfb"
        - "sample_available"
        - "raw_sha256"

    domain_observations:
      purpose: "domain lifecycle history"
      fields:
        - "website_id"
        - "registrable_domain"
        - "registrar"
        - "created_at"
        - "expires_at"
        - "domain_status"
        - "nameservers"
        - "observed_at"
        - "source"

    vulnerability_matches:
      purpose: "version-supported vulnerability mappings"
      fields:
        - "website_id"
        - "technology_observation_id"
        - "vulnerability_id"
        - "source"
        - "match_confidence"
        - "known_exploited"
        - "evidence"
        - "observed_at"
      rules:
        - "Never equate detected product with confirmed vulnerable version."
        - "Never claim exploitability from a generic CVE match."

    market_benchmarks:
      purpose: "commercial context"
      fields:
        - "industry_code"
        - "region"
        - "metric"
        - "period"
        - "value"
        - "source"
        - "source_version"

    entity_links:
      purpose: "explicit identity-resolution edges"
      fields:
        - "left_entity_type"
        - "left_entity_id"
        - "right_entity_type"
        - "right_entity_id"
        - "relationship"
        - "confidence"
        - "evidence_json"
        - "created_at"

  common_provenance_fields:
    required_on_external_observations:
      - "source"
      - "source_record_id"
      - "observed_at"
      - "expires_at"
      - "confidence"
      - "license"
      - "raw_sha256"
      - "ingestion_run_id"

  raw_data_policy:
    preserve_raw_payload: true
    storage_strategy:
      metadata: "SQLite"
      large_raw_payloads: "compressed files/artifacts"
    never:
      - "overwrite raw source values"
      - "discard contradictory source evidence"

entity_resolution_v2:

  objective: >
    Create a deterministic evidence graph connecting authoritative business
    records to websites, domains, places and locations.

  evidence_priority:

    tier_1_authoritative:
      - "exact NZBN"
      - "exact Companies Office identifier"

    tier_2_strong:
      - "same legal name + normalized address"
      - "same legal name + verified website/domain"
      - "same phone + matching business context"

    tier_3_supporting:
      - "trading name"
      - "Overture place identity"
      - "OSM feature identity"
      - "region"
      - "category"

    tier_4_weak:
      - "fuzzy name alone"
      - "same city alone"
      - "similar website text"

  conflict_rules:
    - "Conflicting authoritative IDs must prevent auto-merge."
    - "Parent and branch entities remain separate."
    - "Formatting-only address/name differences are not contradictions."
    - "Service-area businesses are not penalized for missing street address."
    - "Weak single-signal matches cannot reach high confidence."

  registrable_domain:
    implementation: "Public Suffix List"
    mandatory_before:
      - "domain-based deduplication"
      - "email-domain identity comparison"
      - "subdomain consolidation"

web_intelligence_layer:

  objective: >
    Measure not only how a website looks today but its real-user performance,
    lifecycle, technology, historic evolution and change trajectory.

  components:

    lighthouse:
      purpose: "controlled lab testing"
      keep: true

    crux:
      purpose: "real-user field data"
      add: true

    common_crawl:
      purpose: "historic public web evidence"
      add: true

    rdap:
      purpose: "domain lifecycle"
      add_to_canonical_pipeline: true

    technology_history:
      purpose:
        - "CMS/framework evolution"
        - "hosting changes"
        - "major redesign detection"
      add: true

  derived_signals:
    - "website_abandonment_score"
    - "months_since_material_change"
    - "historic_contact_change"
    - "historic_booking_functionality"
    - "technology_age_signal"
    - "domain_age_context"
    - "field_performance_trend"

  rules:
    - "Derived signals must reference underlying observations."
    - "Website inactivity is a commercial signal, not automatically a defect."
    - "Historic snapshots should never be represented as current facts."

market_intelligence_layer:

  objective: >
    Add authoritative NZ market context without contaminating technical audit
    scoring.

  source:
    primary: "Stats NZ Business Demography"

  dimensions:
    - "region"
    - "industry"
    - "enterprise count"
    - "employment"
    - "business births"
    - "business deaths"

  derived_metrics:
    - "regional_business_density"
    - "industry_density"
    - "local_competition_context"
    - "industry_growth_signal"
    - "industry_decline_signal"
    - "relative_opportunity_density"

  scoring_rule:
    technical_audit_score: "website evidence only"
    opportunity_score: "may consume market context"
    identity_confidence: "never consume market attractiveness"

security_intelligence_layer:

  prerequisites:
    - "technology fingerprint"
    - "version evidence where available"

  source_chain:
    - "OSV"
    - "CISA KEV"

  confidence_states:
    - "TECHNOLOGY_DETECTED"
    - "VERSION_INFERRED"
    - "VERSION_CONFIRMED"
    - "VULNERABILITY_CANDIDATE"
    - "VULNERABILITY_SUPPORTED"
    - "KNOWN_EXPLOITED_CONTEXT"

  prohibited_shortcuts:
    - "WordPress detected -> site vulnerable"
    - "plugin detected -> specific CVE confirmed"
    - "CVE exists -> target is exploitable"

  output_language:
    preferred:
      - "Observed"
      - "Inferred"
      - "Potentially applicable"
      - "Version confirmation required"
    avoid:
      - "Definitely vulnerable"
      - "Exploitable"
      - "Compromised"
    exception: "only use stronger wording when evidence independently supports it"

large_scale_ingestion_architecture:

  objective: >
    Handle big datasets without loading raw global sources directly into the
    MoneyMachine SQLite database.

  architecture:

    landing_zone:
      path: "data/raw/"
      contents:
        - "source snapshots"
        - "compressed source files"
        - "download manifests"
        - "checksums"

    staging:
      path: "data/staging/"
      technology:
        preferred:
          - "DuckDB"
          - "Parquet"
      purpose:
        - "filter"
        - "join"
        - "normalize"
        - "dedupe"
        - "select only required NZ records"

    canonical_database:
      technology: "SQLite"
      contents:
        - "normalized business entities"
        - "identity links"
        - "latest observations"
        - "provenance"
        - "workflow state"

    artifacts:
      path: "data/artifacts/"
      contents:
        - "raw observation captures"
        - "historic snapshot evidence"
        - "large source fragments"
        - "checksummed payloads"

  ingestion_manifest:
    fields:
      - "run_id"
      - "source"
      - "source_version"
      - "started_at"
      - "finished_at"
      - "download_sha256"
      - "rows_read"
      - "rows_filtered"
      - "rows_inserted"
      - "rows_updated"
      - "rows_rejected"
      - "license"
      - "status"

  do_not:
    - "insert global Overture dataset directly into SQLite"
    - "insert Common Crawl corpus directly into SQLite"
    - "throw away source IDs"
    - "update records without audit trail"

implementation_plan:

  phase_1:
    name: "Data foundation"
    priority: "P0"
    objective: >
      Build the schema and ingestion infrastructure before acquiring large
      datasets.

    actions:
      - "Create normalized enrichment tables."
      - "Create migration with verified backup requirement."
      - "Add source manifest tables."
      - "Add ingestion run tracking."
      - "Add raw payload checksum support."
      - "Add source licensing field."
      - "Add observation expiration/freshness policy."
      - "Add contradiction preservation."
      - "Add DuckDB dependency/adapter."
      - "Add Parquet staging conventions."

    deliverables:
      - "database migration"
      - "data-source registry"
      - "ingestion manifest schema"
      - "provenance model"
      - "source freshness rules"

    acceptance:
      - "No existing businesses lost."
      - "Migration is reversible through backup."
      - "Raw source provenance survives normalization."
      - "Conflicting observations can coexist."
      - "Existing pipeline tests remain green."

  phase_2:
    name: "Authoritative NZ business spine"
    priority: "P0"
    sources:
      - "Companies Office bulk"
      - "NZBN API"

    actions:
      - "Create Companies Office importer."
      - "Create NZBN API adapter."
      - "Normalize legal names."
      - "Store trading names independently."
      - "Store NZBN as authoritative identifier."
      - "Store entity status."
      - "Store registration/removal dates."
      - "Store BIC classification."
      - "Store authoritative address observations."
      - "Create incremental update/change path."

    acceptance:
      - "Every authoritative ID retains provenance."
      - "No fuzzy matching overwrites authoritative records."
      - "Removed/inactive companies remain historically represented."
      - "Source refreshes are idempotent."

  phase_3:
    name: "Large-scale NZ business discovery"
    priority: "P0"
    primary_source: "Overture Maps Places"
    complementary_source: "OSM"

    actions:
      - "Add Overture source adapter."
      - "Query NZ-only records."
      - "Filter by selected industries/categories."
      - "Preserve Overture/GERS ID."
      - "Store names."
      - "Store location/geometry."
      - "Store taxonomy."
      - "Store operating status."
      - "Store website URLs."
      - "Store phones."
      - "Store social profiles."
      - "Store source confidence."
      - "Feed new candidates through existing DISCOVERED state."
      - "Do not bypass pipeline deduplication."

    recommended_first_regions:
      - "Canterbury"
      - "Auckland"
      - "Wellington"
      - "Waikato"
      - "Bay of Plenty"
      - "Otago"

    recommended_initial_verticals:
      - "plumbers"
      - "electricians"
      - "builders"
      - "roofers"
      - "HVAC"
      - "landscapers"
      - "dentists"
      - "physiotherapists"
      - "accountants"
      - "automotive services"

    acceptance:
      - "Source records remain reproducible."
      - "Duplicates do not create duplicate business entities."
      - "Branch-parent distinction preserved."
      - "Pipeline remains fail-closed for outreach."

  phase_4:
    name: "Entity Resolution V2"
    priority: "P0"

    actions:
      - "Add Public Suffix List resolver."
      - "Calculate registrable_domain."
      - "Create business-domain edges."
      - "Create NZBN-to-domain edges."
      - "Match Overture places to authoritative businesses."
      - "Integrate LINZ address normalization."
      - "Store phone evidence independently."
      - "Add explicit conflict records."
      - "Add confidence scoring."
      - "Add human-review threshold."

    acceptance:
      - "No weak single signal grants HIGH confidence."
      - "Exact NZBN identity wins over fuzzy name."
      - "Parent/branch entities do not auto-collapse."
      - "All entity merges are explainable from stored evidence."

  phase_5:
    name: "Web intelligence"
    priority: "P0_P1"

    actions:
      - "Add CrUX adapter."
      - "Add CrUX History adapter."
      - "Persist field performance observations."
      - "Promote RDAP into canonical pipeline."
      - "Add Common Crawl index lookup."
      - "Create historic snapshot extraction."
      - "Store first_seen/last_seen website evidence."
      - "Track material website changes."
      - "Track technology history."

    acceptance:
      - "Lighthouse and CrUX are reported separately."
      - "Historic evidence is timestamped."
      - "No CrUX data is represented as a failure."
      - "Common Crawl absence is not represented as evidence of inactivity."

  phase_6:
    name: "Market intelligence + scoring"
    priority: "P1"

    actions:
      - "Import Stats NZ industry-region aggregates."
      - "Build industry benchmark table."
      - "Build regional benchmark table."
      - "Compute density metrics."
      - "Compute growth/decline indicators."
      - "Feed market context into opportunity scoring."
      - "Keep audit severity isolated."

    opportunity_formula_target: >
      need
      * business_value
      * contactability
      * fixability
      * confidence
      * market_context
      / delivery_effort

    acceptance:
      - "Technical audit remains deterministic from website evidence."
      - "Market metrics can be replayed from source version."
      - "Opportunity-score inputs are individually visible."

  phase_7:
    name: "Security intelligence + real learning data"
    priority: "P1"

    actions:
      - "Map confirmed technology versions to OSV."
      - "Add CISA KEV enrichment."
      - "Build vulnerability confidence model."
      - "Create manually verified NZ identity gold set."
      - "Create manually verified audit gold set."
      - "Create manually verified opportunity-quality gold set."
      - "Measure precision/recall."
      - "Feed outcome data into self-improvement evaluation."

    gold_datasets:

      identity_gold:
        target_records: 100
        labels:
          - "same_business"
          - "branch"
          - "different_business"
          - "uncertain"

      audit_gold:
        target_sites: 50
        content:
          - "verified defects"
          - "false positives"
          - "missed findings"
          - "finding severity"
          - "evidence correctness"

      opportunity_gold:
        target_businesses: 100
        content:
          - "website need"
          - "commercial relevance"
          - "fixability"
          - "likely service type"
          - "human quality assessment"

    acceptance:
      - "Evaluation data is separate from training/production data."
      - "No self-improvement deployment occurs without measurable improvement."
      - "False-positive rate is tracked."

source_refresh_schedule:

  public_suffix_list:
    cadence: "weekly"

  companies_office:
    cadence: "monthly"

  nzbn:
    cadence: "on enrichment + targeted refresh"

  overture:
    cadence: "each released dataset or monthly"

  osm:
    cadence: "monthly or targeted refresh"

  stats_nz:
    cadence: "when official source updates"

  crux:
    cadence: "weekly for active monitored sites"

  crux_history:
    cadence: "monthly"

  rdap:
    cadence: "90 days unless lifecycle risk warrants earlier"

  common_crawl:
    cadence: "new crawl release or targeted lookup"

  osv:
    cadence: "daily/weekly source refresh"

  cisa_kev:
    cadence: "daily/weekly source refresh"

data_quality_framework:

  required_quality_dimensions:
    - "completeness"
    - "freshness"
    - "confidence"
    - "provenance"
    - "consistency"
    - "identity certainty"

  quality_flags:
    - "MISSING_AUTHORITATIVE_ID"
    - "CONFLICTING_LEGAL_NAME"
    - "CONFLICTING_WEBSITE"
    - "MULTIPLE_POSSIBLE_BUSINESSES"
    - "PARENT_BRANCH_AMBIGUITY"
    - "STALE_SOURCE"
    - "INVALID_DOMAIN"
    - "ADDRESS_CONFLICT"
    - "PHONE_CONFLICT"
    - "CATEGORY_CONFLICT"
    - "SOURCE_UNAVAILABLE"

  data_confidence:
    HIGH:
      requirements:
        - "authoritative exact ID"
        - "or multiple independent strong signals"

    MEDIUM:
      requirements:
        - "multiple non-authoritative matching signals"

    LOW:
      requirements:
        - "single weak or fuzzy signal"

    CONFLICT:
      requirements:
        - "material contradiction requiring review"

commercial_intelligence_examples:

  example_signals:
    website_abandoned:
      data:
        - "Common Crawl history"
        - "current crawl"
      commercial_value: "HIGH"

    poor_real_user_performance:
      data:
        - "CrUX"
        - "Lighthouse"
      commercial_value: "HIGH"

    strong_business_weak_site:
      data:
        - "NZBN/Companies Office"
        - "Stats NZ"
        - "audit findings"
      commercial_value: "VERY_HIGH"

    new_business_old_website_stack:
      data:
        - "registration date"
        - "technology age"
        - "audit evidence"
      commercial_value: "MEDIUM_HIGH"

    active_business_no_functioning_conversion_path:
      data:
        - "business status"
        - "browser audit"
        - "conversion detection"
      commercial_value: "VERY_HIGH"

    confirmed_outdated_vulnerable_technology:
      data:
        - "version-confirmed technology"
        - "OSV"
        - "CISA KEV"
      commercial_value: "HIGH"
      human_review: true

first_five_implementation_targets:

  order:
    1:
      source: "Companies Office + NZBN"
      reason: >
        Establish authoritative NZ entity identity before ingesting huge
        discovery datasets.

    2:
      source: "Overture Maps Places"
      reason: >
        Supplies the biggest immediate increase in legitimate scalable local
        business discovery and enrichment.

    3:
      source: "Public Suffix List + normalized entity schema"
      reason: >
        Prevents domain identity mistakes and ensures enrichment data has a
        correct home.

    4:
      source: "CrUX"
      reason: >
        Gives WEBSITE-AUDITOR credible real-user performance evidence rather
        than relying only on lab testing.

    5:
      source: "Stats NZ"
      reason: >
        Adds authoritative market context and greatly improves opportunity
        prioritization.

  after_foundation:
    6: "LINZ"
    7: "RDAP"
    8: "Common Crawl"
    9: "OSV"
    10: "CISA KEV"

suggested_repo_structure:

  paths:

    data:
      raw: "data/raw/"
      staging: "data/staging/"
      cache: "data/cache/"
      artifacts: "data/artifacts/"
      manifests: "data/manifests/"

    source_adapters:
      root: "money-machine/data_sources/"
      files:
        - "base.py"
        - "companies_office.py"
        - "nzbn.py"
        - "overture.py"
        - "osm.py"
        - "linz.py"
        - "stats_nz.py"
        - "crux.py"
        - "rdap.py"
        - "common_crawl.py"
        - "osv.py"
        - "cisa_kev.py"
        - "public_suffix.py"

    entity_intelligence:
      root: "money-machine/intelligence/"
      files:
        - "entity_resolution.py"
        - "domain_identity.py"
        - "address_resolution.py"
        - "market_context.py"
        - "web_history.py"
        - "vulnerability_context.py"

    tests:
      root: "toolkit_tests/data/"
      files:
        - "test_companies_office.py"
        - "test_nzbn.py"
        - "test_overture.py"
        - "test_psl_domains.py"
        - "test_entity_resolution.py"
        - "test_crux.py"
        - "test_stats_nz.py"
        - "test_common_crawl.py"
        - "test_osv_mapping.py"

suggested_cli:

  commands:

    source_status:
      command: "./mm data-source-status"
      purpose: "show freshness/status of each external source"

    ingest:
      examples:
        - "./mm data-ingest companies-office"
        - "./mm data-ingest overture --country NZ"
        - "./mm data-ingest stats-nz"

    enrich:
      examples:
        - "./mm enrich-business BUSINESS_ID"
        - "./mm enrich-domain example.co.nz"

    reconcile:
      examples:
        - "./mm entity-reconcile BUSINESS_ID"
        - "./mm entity-review --conflicts"

    discovery:
      examples:
        - "./mm discover-overture --region Canterbury --category plumber"
        - "./mm discover-overture --region Auckland --category electrician"

    field_performance:
      example:
        - "./mm crux BUSINESS_ID"

    web_history:
      example:
        - "./mm web-history BUSINESS_ID"

    vulnerability_context:
      example:
        - "./mm vulnerability-context BUSINESS_ID"

    data_quality:
      examples:
        - "./mm data-quality"
        - "./mm data-quality --conflicts"

big_data_performance_strategy:

  preferred_engine:
    staging_and_analysis: "DuckDB"
    runtime_state: "SQLite"

  storage_formats:
    source_bulk:
      - "Parquet"
      - "GeoParquet"
      - "compressed CSV when unavoidable"

  rules:
    - "Filter early."
    - "Project only required columns."
    - "Partition by source/date/region where useful."
    - "Do heavy joins in DuckDB."
    - "Store only canonical normalized results in SQLite."
    - "Keep bulk datasets outside Git."
    - "Track hashes and manifests instead of committing source data."

  sqlite_scaling:
    keep_until:
      - "measured write-contention bottleneck"
      - "measured query bottleneck"
    do_not_migrate_to_postgres_merely_for:
      - "large read-only Parquet datasets"
      - "bulk analytical joins"

expected_business_outcome:

  before:
    capability: >
      Find websites, audit them accurately, determine defects, prepare
      remediation/demo/quote materials and queue human-reviewed opportunities.

  after:
    capability: >
      Build a continuously refreshed NZ business graph that knows who a
      business is, where it operates, what industry it belongs to, which
      websites and domains belong to it, how those sites perform for real
      users, how they have changed over time, what technologies they use,
      how the business compares with its market, and which opportunities have
      the strongest evidence and commercial relevance.

success_metrics:

  identity:
    - ">= 95% precision on HIGH-confidence identity matches"
    - "<= 1% incorrect authoritative merges"
    - "100% provenance coverage for external identifiers"

  discovery:
    - "source-specific ingestion counts recorded"
    - "duplicate rate measured"
    - "rejection reasons typed"
    - "branch-parent conflicts visible"

  audit:
    - "CrUX field data used whenever available"
    - "lab and field metrics never conflated"
    - "finding precision tracked against gold set"

  market:
    - "all market-score inputs source-versioned"
    - "technical score unaffected by commercial context"

  vulnerability:
    - "100% vulnerability claims trace to technology/version evidence"
    - "KEV status never used without supported CVE mapping"

  data:
    - "100% external observations carry provenance"
    - "source refresh age visible"
    - "no bulk source silently overwrites another source"

  operations:
    - "zero paid data/API spend by default"
    - "zero external outreach caused by data ingestion"
    - "all ingestion jobs resumable/replayable"

final_execution_order:

  - "1. Create enrichment/provenance schema."
  - "2. Add DuckDB + Parquet staging layer."
  - "3. Add Public Suffix List domain normalization."
  - "4. Import Companies Office bulk baseline."
  - "5. Add NZBN verification/enrichment."
  - "6. Build authoritative identity graph."
  - "7. Add Overture NZ ingestion."
  - "8. Add OSM complementary enrichment."
  - "9. Add LINZ address/location normalization."
  - "10. Upgrade entity-resolution confidence logic."
  - "11. Add CrUX + CrUX History."
  - "12. Promote RDAP into canonical auditor."
  - "13. Add Stats NZ market benchmarks."
  - "14. Add targeted Common Crawl history."
  - "15. Complete technology/version fingerprint layer."
  - "16. Add OSV mappings."
  - "17. Add CISA KEV enrichment."
  - "18. Build real NZ identity/audit/opportunity gold datasets."
  - "19. Measure accuracy and false-positive rates."
  - "20. Feed measured outcomes into the existing self-improvement loop."

do_not_do_yet:

  - "Do not ingest millions of records before schema migration."
  - "Do not put global Overture data directly into MoneyMachine SQLite."
  - "Do not replace Lighthouse with CrUX; keep both."
  - "Do not treat missing CrUX data as a defect."
  - "Do not auto-merge companies based on fuzzy name alone."
  - "Do not flatten branches into parent companies."
  - "Do not use RDAP/WHOIS as a mass contact harvesting system."
  - "Do not use charity emails for marketing."
  - "Do not use public Nominatim as a high-volume production backend."
  - "Do not depend on public Overpass for continuous bulk discovery."
  - "Do not claim vulnerability from technology detection alone."
  - "Do not migrate SQLite runtime state to heavier infrastructure without measured need."
  - "Do not enable paid APIs to solve a data gap while free/open alternatives remain suitable."

recommended_next_branch:

  branch: "upgrade/v42-data-intelligence-foundation"

  first_commit:
    name: "feat(data): add normalized enrichment and provenance schema"

  second_commit:
    name: "feat(domain): add PSL-aware registrable domain resolution"

  third_commit:
    name: "feat(data): add DuckDB bulk-source staging framework"

  fourth_commit:
    name: "feat(nz): add Companies Office bulk importer"

  fifth_commit:
    name: "feat(nzbn): add authoritative NZBN enrichment adapter"

  sixth_commit:
    name: "feat(discovery): add Overture NZ places ingestion"

  release_gate:
    - "existing tests green"
    - "new source adapter tests green"
    - "migration backup/restore proven"
    - "no existing identity records lost"
    - "no paid API calls"
    - "no external sends"
    - "provenance completeness = 100%"