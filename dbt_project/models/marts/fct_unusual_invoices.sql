-- Statistical detector: invoices whose total is far from their partner's usual amount.
with invoices as (
    select
        partner_id,
        invoice_number,
        sum(line_amount) as total
    from {{ ref('fct_invoice_lines') }}
    group by 1, 2
),
partner_stats as (
    select
        partner_id,
        avg(total) as mu,
        stddev_samp(total) as sd
    from invoices
    group by 1
)
select
    i.partner_id,
    i.invoice_number,
    round(i.total, 2) as total,
    round(s.mu, 2) as partner_mean,
    round((i.total - s.mu) / s.sd, 2) as z_score
from invoices i
join partner_stats s using (partner_id)
where s.sd > 0
  and abs((i.total - s.mu) / s.sd) > 2
