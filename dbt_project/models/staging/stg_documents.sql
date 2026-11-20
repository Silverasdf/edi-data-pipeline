select
    file_name,
    partner as partner_id,
    tx_type,
    control_number,
    doc_number,
    po_number,
    strptime(doc_date, '%Y%m%d')::date as doc_date,
    total_cents / 100.0 as total_amount,
    loaded_at
from {{ source('raw', 'documents') }}
