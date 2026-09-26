import csv

from django.http import HttpResponse
from rest_framework.decorators import action


class ExportMixin:
    """Adds `GET <list url>/export/`: the rows the caller can list, as CSV with an `id,title` header."""

    @action(detail=False)
    def export(self, request):
        response = HttpResponse(content_type="text/csv")
        writer = csv.writer(response)
        writer.writerow(["id", "title"])
        for row in self.filter_queryset(self.get_queryset()):
            writer.writerow([row.pk, row.title])
        return response
