-- Singular test: returns rows only when something is wrong.
select * from {{ ref('stg_document_lines') }}
where qty <= 0 or unit_price <= 0
