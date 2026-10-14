from __future__ import annotations

from enum import Enum
from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from app.services.linear_gateway import call_linear_gateway


class LinearLookupKind(str, Enum):
    teams = "teams"
    users = "users"
    projects = "projects"
    statuses = "statuses"
    cycles = "cycles"
    labels = "labels"


READ_ONLY = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
MUTATION = ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=False)
ARCHIVE = ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=True, openWorldHint=False)


def register(server: FastMCP) -> None:
    @server.tool(name="linear-get-issue", description="Read a Linear issue by UUID or identifier such as REV-27.", annotations=READ_ONLY)
    def linear_get_issue(issue: str) -> dict[str, Any]:
        return call_linear_gateway("get_issue", {"issue": issue})

    @server.tool(name="linear-list-issues", description="List Linear issues with an optional Linear IssueFilter object.", annotations=READ_ONLY)
    def linear_list_issues(first: int = 25, filter: dict[str, Any] | None = None) -> dict[str, Any]:
        return call_linear_gateway("list_issues", {"first": first, "filter": filter or {}})

    @server.tool(
        name="linear-lookup",
        description="List Linear teams, users, projects, workflow statuses, cycles, or issue labels. Statuses and cycles require a team UUID.",
        annotations=READ_ONLY,
    )
    def linear_lookup(kind: LinearLookupKind, team: str | None = None, first: int = 50) -> dict[str, Any]:
        return call_linear_gateway("lookup", {"kind": kind.value, "team": team, "first": first})

    @server.tool(name="linear-list-comments", description="List comments on a Linear issue.", annotations=READ_ONLY)
    def linear_list_comments(issue: str, first: int = 50) -> dict[str, Any]:
        return call_linear_gateway("list_comments", {"issue": issue, "first": first})

    @server.tool(
        name="linear-create-issue",
        description="Create a Linear issue. fields is Linear IssueCreateInput and must include teamId and title. Deletion is unavailable.",
        annotations=MUTATION,
    )
    def linear_create_issue(fields: dict[str, Any]) -> dict[str, Any]:
        return call_linear_gateway("create_issue", {"fields": fields})

    @server.tool(
        name="linear-update-issue",
        description="Update a Linear issue using IssueUpdateInput fields. Supports status, priority, assignee, project, cycle, labels, due date, and more. Deletion is impossible.",
        annotations=MUTATION,
    )
    def linear_update_issue(issue: str, fields: dict[str, Any]) -> dict[str, Any]:
        return call_linear_gateway("update_issue", {"issue": issue, "fields": fields})

    @server.tool(
        name="linear-save-comment",
        description="Create a comment, reply with parent_id, or update an existing comment with comment_id.",
        annotations=MUTATION,
    )
    def linear_save_comment(body: str, issue: str | None = None, comment_id: str | None = None, parent_id: str | None = None) -> dict[str, Any]:
        return call_linear_gateway("save_comment", {"body": body, "issue": issue, "commentId": comment_id, "parentId": parent_id})

    @server.tool(name="linear-archive-issue", description="Archive an issue reversibly. This does not delete it.", annotations=ARCHIVE)
    def linear_archive_issue(issue: str) -> dict[str, Any]:
        return call_linear_gateway("archive_issue", {"issue": issue})

    @server.tool(name="linear-unarchive-issue", description="Restore an archived Linear issue.", annotations=MUTATION)
    def linear_unarchive_issue(issue: str) -> dict[str, Any]:
        return call_linear_gateway("unarchive_issue", {"issue": issue})

    @server.tool(name="linear-create-issue-relation", description="Create an issue relationship using IssueRelationCreateInput fields.", annotations=MUTATION)
    def linear_create_issue_relation(fields: dict[str, Any]) -> dict[str, Any]:
        return call_linear_gateway("create_issue_relation", {"fields": fields})

    @server.tool(name="linear-create-link-attachment", description="Attach an existing URL to an issue using AttachmentCreateInput fields.", annotations=MUTATION)
    def linear_create_link_attachment(fields: dict[str, Any]) -> dict[str, Any]:
        return call_linear_gateway("create_attachment", {"fields": fields})
