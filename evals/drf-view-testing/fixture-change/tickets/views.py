from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Count
from django.utils import timezone
from rest_framework import serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from tickets.models import Membership, Ticket
from tickets.notifications import notify_ticket_closed
from tickets.permissions import HasRole
from tickets.serializers import TicketSerializer


class TicketViewSet(viewsets.ModelViewSet):
    """Tickets of the caller's company (`request.user.membership.company`); other companies' tickets are never visible.

    - Everyone in the company reads. Agents and admins create, edit, and close. Only admins delete and assign.
    - The list is newest first and hides archived tickets; `?archived=true` lists only the archived ones instead.
      `?status=open|closed` filters by status.
    - Creating sets the company and `created_by` from the caller. Deleting archives the ticket instead of removing it.
    - `POST /tickets/{id}/close/` closes an open ticket, stamps `closed_at`, and notifies the creator once the
      transaction commits. Closing a closed ticket is a 400.
    - `POST /tickets/{id}/assign/` with `{"assignee": <user id>}` assigns a member of the same company; anyone else is a 400.
    - `GET /tickets/stats/` returns `{"open": n, "closed": n}` for the company's unarchived tickets.
    """

    serializer_class = TicketSerializer

    def get_permissions(self):
        if self.action in ("list", "retrieve", "stats"):
            roles = (Membership.Role.VIEWER, Membership.Role.AGENT, Membership.Role.ADMIN)
        elif self.action in ("destroy", "assign"):
            roles = (Membership.Role.ADMIN,)
        else:
            roles = (Membership.Role.AGENT, Membership.Role.ADMIN)
        return [IsAuthenticated(), HasRole(roles)]

    @property
    def company(self):
        return self.request.user.membership.company

    def get_queryset(self):
        if self.request.query_params.get("archived") == "true":
            tickets = Ticket.objects.filter(company=self.company, archived=True)
        else:
            tickets = Ticket.objects.filter(company=self.company, archived=False)
        if status_filter := self.request.query_params.get("status"):
            tickets = tickets.filter(status=status_filter)
        return tickets.select_related("assignee").order_by("-created_at", "-pk")

    def perform_create(self, serializer):
        serializer.save(company=self.company, created_by=self.request.user)

    def perform_destroy(self, ticket):
        ticket.archived = True
        ticket.save(update_fields=["archived"])

    @action(detail=True, methods=["post"])
    def close(self, request, pk=None):
        ticket = self.get_object()
        if ticket.status == Ticket.Status.CLOSED:
            return Response({"detail": "Ticket is already closed."}, status=status.HTTP_400_BAD_REQUEST)
        ticket.status = Ticket.Status.CLOSED
        ticket.closed_at = timezone.now()
        ticket.save(update_fields=["status", "closed_at"])
        transaction.on_commit(lambda: notify_ticket_closed(ticket.pk))
        return Response(TicketSerializer(ticket).data)

    @action(detail=True, methods=["post"])
    def assign(self, request, pk=None):
        ticket = self.get_object()
        user_id = request.data.get("assignee")
        assignee = get_user_model().objects.filter(pk=user_id, membership__company=self.company).first()
        if assignee is None:
            raise serializers.ValidationError({"assignee": "Assign a member of this company."})
        ticket.assignee = assignee
        ticket.save(update_fields=["assignee"])
        return Response(TicketSerializer(ticket).data)

    @action(detail=False)
    def stats(self, request):
        counts = dict(
            Ticket.objects.filter(company=self.company, archived=False)
            .values_list("status")
            .annotate(n=Count("pk"))
            .values_list("status", "n")
        )
        return Response({"open": counts.get("open", 0), "closed": counts.get("closed", 0)})
