import uuid

from django.db import models


class BaseModel(models.Model):
    """Abstract base for domain models.

    UUID primary keys keep identifiers safe to expose in the public mobile API,
    where sequential integers would leak order volume and invite enumeration.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True
