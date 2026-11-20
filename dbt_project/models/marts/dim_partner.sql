select
    partner_id,
    partner_name
from {{ ref('partners') }}