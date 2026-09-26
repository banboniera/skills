from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import filters, serializers, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import SAFE_METHODS, BasePermission, IsAuthenticated
from rest_framework.response import Response

from documents.models import Document, Member


class DocumentSerializer(serializers.ModelSerializer):
    owner_name = serializers.CharField(source="owner.username", read_only=True)

    class Meta:
        model = Document
        fields = ["id", "title", "body", "visibility", "owner", "owner_name", "created_at"]
        read_only_fields = ["created_at"]


class IsMemberWithRole(BasePermission):
    """Readers read; editors and admins also write; only admins restore."""

    def has_permission(self, request, view):
        member = getattr(request.user, "member", None)
        if member is None:
            return False
        if view.action == "restore":
            return member.role == Member.Role.ADMIN
        return request.method in SAFE_METHODS or member.role in (Member.Role.EDITOR, Member.Role.ADMIN)


class IsOwnerOrAdmin(BasePermission):
    """Only a document's owner or a workspace admin may change or delete it."""

    def has_object_permission(self, request, view, document):
        if request.method in ("PUT", "PATCH"):
            return document.owner_id == request.user.pk or request.user.member.role == Member.Role.ADMIN
        return True


class DocumentViewSet(viewsets.ModelViewSet):
    """Documents of the caller's workspace (`request.user.member.workspace`).

    - A caller sees the workspace's documents with workspace visibility plus their own private ones; other workspaces'
      documents and others' private documents do not exist for them (404). Deleted documents are hidden.
    - Readers read. Editors and admins create; the owner is always the creator. Only the owner or an admin may edit
      or delete a document. Deleting sets `deleted_at` instead of removing the row.
    - `?search=` matches titles; `?ordering=title|-title|created_at|-created_at` orders; the default is newest first.
    - `POST /documents/{id}/restore/` (admins only) restores a deleted document of the workspace.
    """

    serializer_class = DocumentSerializer
    permission_classes = [IsAuthenticated, IsMemberWithRole, IsOwnerOrAdmin]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["title"]
    ordering_fields = ["title", "created_at"]

    @property
    def workspace(self):
        return self.request.user.member.workspace

    def get_queryset(self):
        return (
            Document.objects.filter(workspace=self.workspace, deleted_at__isnull=True)
            .select_related("owner")
            .order_by("-created_at", "-pk")
        )

    def list(self, request, *args, **kwargs):
        documents = self.filter_queryset(self.get_queryset()).filter(
            Q(visibility=Document.Visibility.WORKSPACE) | Q(owner=request.user)
        )
        page = self.paginate_queryset(documents)
        return self.get_paginated_response(self.get_serializer(page, many=True).data)

    def perform_create(self, serializer):
        serializer.save(workspace=self.workspace)

    def perform_destroy(self, document):
        document.deleted_at = timezone.now()
        document.save(update_fields=["deleted_at"])

    @action(detail=True, methods=["post"])
    def restore(self, request, pk=None):
        document = get_object_or_404(Document, pk=pk, workspace=self.workspace, deleted_at__isnull=False)
        document.deleted_at = None
        document.save(update_fields=["deleted_at"])
        return Response(self.get_serializer(document).data)
