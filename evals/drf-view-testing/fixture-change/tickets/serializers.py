from rest_framework import serializers

from tickets.models import Ticket


class TicketSerializer(serializers.ModelSerializer):
    assignee_name = serializers.CharField(source="assignee.username", read_only=True, default=None)

    class Meta:
        model = Ticket
        fields = ["id", "title", "status", "assignee", "assignee_name", "created_by", "created_at", "closed_at"]
        read_only_fields = ["status", "assignee", "created_by", "created_at", "closed_at"]
