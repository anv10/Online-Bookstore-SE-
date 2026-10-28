# Listing moderation: issue #19

Implements FR-12 for listings, using the current Django/PostgreSQL application structure. Read alongside Documents/SRS_Online_Bookstore.docx, SecurityRequirements_Online_Bookstore.docx, UseCaseFlow.docx (UC16), ArchitectureDiagram.pdf and TestPlan_Online_Bookstore.docx. The architecture PDF predates the selected framework; the README's Django/PostgreSQL decision remains authoritative.

## Setup and workflow

1. Apply migrations using `python manage.py migrate`.
2. Configure EMAIL_HOST, EMAIL_PORT, EMAIL_HOST_USER, EMAIL_HOST_PASSWORD, EMAIL_USE_TLS and DEFAULT_FROM_EMAIL in your environment, using a TLS-enabled SMTP provider. No console email backend is used, because verification codes must not be written to logs. Do not commit credentials. Verify delivery in the target environment before use.
3. Provision trusted moderators outside public registration. They need an active account with an email, `is_staff=True`, and the `catalog.change_book` permission. Superusers also qualify. Staff status alone and permission alone are each insufficient.
4. Sign in and visit `/moderation/`. Request a six digit email code and verify it. The code expires after ten minutes, is single-use, and is bound to the requesting session. Five failed guesses exhaust a code. Requests are limited to five per account per hour across sessions. Successful verification grants access to moderation for thirty minutes in that session; logout or expiry requires verification again.
5. The queue defaults to pending listings. Review book details and images, select Approve, Suspend or Remove, enter a reason, and submit. Filtering also allows review of approved or suspended listings. Removed listings cannot be reinstated through these endpoints.
6. Approval requires an active seller. Suspension/removal hides the listing from catalog and detail pages. Removal is a status change, preserving the row and historical order references.
7. Each changed status creates one ModerationEvent with actor, target, old/new status, reason and timestamp in the same transaction. Duplicate/stale actions are rejected without another event. Sellers see their own latest twenty decision notifications on their listings page, including removed books. Other sellers cannot see those notices.

Status is read-only in the existing Django BookAdmin and hard deletion is disabled there, so its form cannot bypass decision reasons, verification and audit creation. Challenge records are not exposed in Django admin. Audit events have no application write/delete endpoints. Production database access and backup/retention policies must protect the underlying audit table (SEC-32); database owners can still change database records directly.

## Validation and test plan mapping

Local validation: Python 3.12.14, Django 5.2.18, in-memory SQLite override used only by the validation process. 101 tests passed with 99% statement coverage (configured minimum: 70%); Django system checks and migration drift check passed. No SQLite configuration is committed. Run the repository PostgreSQL workflow before marking this ready for merge. SQLite cannot validate PostgreSQL row-lock behavior or concurrent transactions.

The feature adds request-level tests for authorization, email verification, expiry, replay/session binding, failed delivery, request and guessing limits, CSRF, required reason, invalid decisions, duplicate and stale decisions, visibility, audit rollback, order preservation, escaped content, seller privacy and the concurrent seller-edit regression.

| Submitted test ID | Evidence in catalog/tests/test_moderation.py | Limit |
| --- | --- | --- |
| FR-12_UT02 | test_duplicate_and_removed_listing_cannot_be_reinstated | Duplicate approval produces no additional audit event |
| FR-12_UT03 | test_reason_invalid_target_and_stale_decision_rejected | UI uses Suspend/Remove rather than a separate Reject action |
| FR-12_IT02 | test_order_history_survives_moderation_removal | Soft removal preserves the OrderItem FK |
| FR-12_IT03 | test_approve_suspend_remove_are_audited_and_hide_listing | Events include admin, listing, reason, time and both states |
| FR-12_ST01 | test_approve_suspend_remove_are_audited_and_hide_listing | Pending queue is available; flagged/report workflow is not implemented |
| FR-12_ST02 | test_anonymous_and_non_admin_access; test_permission_alone_and_staff_alone_do_not_grant_admin_access | Server-side access checks on every endpoint |
| FR-12_UT01 / IT01 | Outside issue #19 | Account suspension/removal belongs to teammate issue #20 |

Original submitted test plan statuses remain Pending. This addendum reports automated local evidence rather than claiming browser/system/PostgreSQL sign-off.

## Deviations and remaining checks

- UC16 owner notification is an in-app seller notice, not an outbound moderation email. OTP verification does use email.
- The second factor protects these moderation endpoints. Other pre-existing Django admin functions do not gain MFA in this change; do not claim SEC-14 for the entire application.
- No flagged-report/reject workflow is added; the issue's Pending/Approve/Suspend/Remove workflow is implemented.
- Staff provisioning uses Django staff + permission checks, matching existing permission-based seller provisioning; public users cannot grant themselves these privileges.
- Real SMTP delivery, PostgreSQL migrations/tests/locking, Chrome/Firefox/Safari/Edge and mobile checks, deployment TLS, protected audit storage and human owner review remain unverified. Keep the PR draft until required validation and review are complete.
- AI-assisted implementation. Assigned team member submission and human review remain separate steps; no human review is represented by automated checks.
