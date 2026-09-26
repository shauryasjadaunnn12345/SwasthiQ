from django.db import models


class BillingDay(models.Model):
    """
    One clinic's billing log for one calendar date.

    Re-ingesting the same (clinic_id, date) pair replaces this row's data
    atomically -- see billing.services.ingestion.ingest_billing_log -- so a
    corrected re-upload never leaves stale or duplicated rows behind.
    """

    clinic_id = models.CharField(max_length=64)
    log_date = models.DateField()
    ingested_at = models.DateTimeField(auto_now=True)
    rejected_rows = models.JSONField(default=list)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["clinic_id", "log_date"], name="unique_clinic_day"
            )
        ]
        ordering = ["-log_date"]

    def __str__(self):
        return f"{self.clinic_id} / {self.log_date.isoformat()}"


class BillingRow(models.Model):
    """A single validated visit row belonging to a BillingDay."""

    PAYMENT_MODES = [("cash", "cash"), ("card", "card"), ("upi", "upi")]

    day = models.ForeignKey(BillingDay, on_delete=models.CASCADE, related_name="rows")
    visit_id = models.CharField(max_length=64)
    timestamp = models.DateTimeField()
    doctor_id = models.CharField(max_length=64, blank=True, default="")
    line_items = models.JSONField(default=list)
    payment_mode = models.CharField(max_length=8, choices=PAYMENT_MODES)
    amount_paid_paise = models.BigIntegerField()
    discount_paise = models.BigIntegerField(default=0)
    is_refund = models.BooleanField(default=False)

    class Meta:
        ordering = ["timestamp"]

    def __str__(self):
        return self.visit_id
