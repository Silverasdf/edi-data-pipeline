select
    file_name,
    partner as partner_id,
    tx_type,
    error_code,
    detail,
    loaded_at
from {{ source('raw', 'rejects') }}
