select
    partner_id,
    error_code,
    cast(loaded_at as date) as load_date,
    count(distinct file_name) as rejected_files
from {{ ref('stg_rejects') }}
group by 1, 2, 3
