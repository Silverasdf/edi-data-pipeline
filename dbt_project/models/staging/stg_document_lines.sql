select
    file_name,
    tx_type,
    line_no,
    qty,
    unit_price,
    sku,
    qty * unit_price as line_amount
from {{ source('raw', 'document_lines') }}
