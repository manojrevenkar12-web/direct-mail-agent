select
    company_id,
    company_type,
    status,
    sector,
    age_months,
    existing_customer,
    open_application,
    days_since_decline,
    objected,
    gone_away,
    mps_director,
    days_since_last_letter,
    days_since_holdout,
    letters_last_365
from {{ source('raw', 'companies') }}
