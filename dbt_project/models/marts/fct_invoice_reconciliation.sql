with ordered as (
    select po_number, partner_id, sum(line_amount) as ordered_amount
    from {{ ref('fct_order_lines') }}
    group by 1, 2
),
invoiced as (
    select po_number, partner_id, sum(line_amount) as invoiced_amount
    from {{ ref('fct_invoice_lines') }}
    group by 1, 2
)
select
    coalesce(o.po_number, i.po_number) as po_number,
    coalesce(o.partner_id, i.partner_id) as partner_id,
    o.ordered_amount,
    i.invoiced_amount,
    round(coalesce(i.invoiced_amount, 0) - coalesce(o.ordered_amount, 0), 2) as difference,
    case
        when o.po_number is null then 'invoice_without_po'
        when i.po_number is null then 'po_without_invoice'
        when abs(i.invoiced_amount - o.ordered_amount) < 0.01 then 'matched'
        else 'mismatch'
    end as status
from ordered o
full outer join invoiced i using (po_number)
