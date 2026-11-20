# edi-pipeline

## Synthetic EDI security extension

This project adds two security checks to the synthetic X12 pipeline: a rule that rejects messages from senders outside the known-partner list (`UNKNOWN_SENDER`), and a dbt model that flags statistically unusual invoice totals per partner.

### Detection results

Measured with `python -m edi_pipeline.security_eval` on a seeded 600-file batch (run date 2026-11-19):

| Check | Injected | Caught | Clean items flagged by mistake |
| --- | ---: | ---: | ---: |
| `UNKNOWN_SENDER` (spoofed ISA06 sender) | 12 files | 12 | 0 files |
| `fct_unusual_invoices` (z-score > 2) | 4 invoices | 3 | 6 invoices |

### Limits

The z-score model is a screen, not a fraud detector:

- It has no business context. A large but legitimate invoice (approved price change, new contract, rush order) is indistinguishable from an inflated one, which is why six clean invoices were flagged in this run.
- It misses small, gradual overbilling that stays inside a partner's normal spread, and it looks only at invoice totals, not unit prices, quantities, dates, or duplicate invoices across partners.
- It cannot catch a spoofed sender that uses an ID already on the known-partner list, or a compromised legitimate partner. The `UNKNOWN_SENDER` rule only checks the ID in ISA06, not certificates, signatures, or IP origin.
- It cannot detect fabricating partners' invoices that are individually ordinary and reconcile to a purchase order.
- With few invoices for a partner, `stddev_samp` is unstable or NULL; the model skips partners with zero variance, so a lone outlier there is missed.
- The threshold of 2 standard deviations is a convention applied to synthetic data. It is not calibrated against labelled real-world fraud, so both the miss rate and the false-positive rate would need to be re-measured on production data.
