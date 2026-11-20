select
    d.po_number,
    d.partner_id,
    d.doc_date as order_date,
    l.line_no,
    l.sku,
    l.qty,
    l.unit_price,
    l.line_amount
from {{ ref('stg_documents') }} d
join {{ ref('stg_document_lines') }} l using (file_name)
where d.tx_type = '850'
