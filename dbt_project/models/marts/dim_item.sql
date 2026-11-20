select
    sku,
    round(avg(unit_price), 2) as avg_unit_price,
    count(*) as times_ordered_or_invoiced
from {{ ref('stg_document_lines') }}
group by sku