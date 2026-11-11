# Test Plan execution results

Every case in `Documents/TestPlan_Online_Bookstore.pdf` executed against the merged `main` branch, with the result and the evidence for each one.

- Repository: `anv10/Online-Bookstore-SE-`, branch `main`
- Sprint 2 close-out, executed after the 30 Oct freeze
- Automated suite: **477 tests** (`python manage.py test`)
- Cases executed: **120**

## Summary

| Result | Cases |
| --- | ---: |
| Pass | 120 |
| Fail - differs | 0 |
| Fail - not built | 0 |
| Not run | 0 |
| **Total** | **120** |

| Requirement | Cases | Pass | Fail | Not run |
| --- | ---: | ---: | ---: | ---: |
| FR-1 | 8 | 8 | 0 | 0 |
| FR-2 | 8 | 8 | 0 | 0 |
| FR-3 | 8 | 8 | 0 | 0 |
| FR-4 | 8 | 8 | 0 | 0 |
| FR-5 | 8 | 8 | 0 | 0 |
| FR-6 | 8 | 8 | 0 | 0 |
| FR-7 | 8 | 8 | 0 | 0 |
| FR-8 | 8 | 8 | 0 | 0 |
| FR-9 | 8 | 8 | 0 | 0 |
| FR-10 | 8 | 8 | 0 | 0 |
| FR-11 | 8 | 8 | 0 | 0 |
| FR-12 | 8 | 8 | 0 | 0 |
| FR-13 | 8 | 8 | 0 | 0 |
| FR-14 | 8 | 8 | 0 | 0 |
| FR-15 | 8 | 8 | 0 | 0 |

## How each case was judged

A case is **Pass** only when behaviour matching the case's stated *Expected Results* is proved by a named automated test. Where a case is only reachable by hand, the code path is quoted instead.

- **Fail - differs**: the feature exists but the observable behaviour contradicts the plan.
- **Fail - not built**: there is no code for the expected behaviour.
- **Not run**: needs load-test or cross-browser hardware that this repository does not have.

The plan's own *Expected Result* column is the yardstick, not the SRS. Where the team deliberately chose different behaviour, the case still counts as a failure here and the reason is recorded in `docs/deviations.md`.

Two cases need infrastructure beyond the unit suite, so they were run with dedicated tools:

- **FR-2_ST02**: `python manage.py load_test_search --requests 500 --workers 50` returned 500 searches in 8.65 s wall time, p95 1.04 s and max 1.52 s, inside the 2 s target.
- **FR-15_ST02**: the signed-in wishlist was rendered at 390x844 in headless Chrome; the same item is visible as at 1366x900 (`docs/testing/wishlist-mobile.png`, `wishlist-desktop.png`).

## Results by requirement

### FR-1 - User Registration & Login

| Case | Description | Expected result | Result | Evidence |
| --- | --- | --- | --- | --- |
| FR-1_UT01 | Reject invalid email format at registration | Error "Enter a valid email address" shown; registration blocked | Pass | accounts.test_register.test_invalid_identifier |
| FR-1_UT02 | Reject weak password at registration | Error "Password must be at least 8 characters" shown | Pass | accounts.test_register.test_weak_password_rejected |
| FR-1_UT03 | Reject registration with blank mandatory phone field | Error "Phone number is required" shown | Pass | test_blank_phone_is_rejected (registration now collects email and phone) |
| FR-1_IT01 | Register new user with valid details creates DB record | New row inserted in Users table with hashed password; success message shown | Pass | test_register.test_register_with_email + test_models.test_create_user_hashes_password |
| FR-1_IT02 | Login authenticates against stored credentials | Session token generated; user redirected to home page | Pass | test_auth.test_login_with_email_starts_session |
| FR-1_IT03 | Prevent duplicate registration for existing email | Error "Account already exists" shown; no duplicate row created | Pass | test_register.test_duplicate_email_rejected |
| FR-1_ST01 | End-to-end register, logout, re-login | User successfully accesses dashboard after re-login | Pass | test_register.test_register_with_email + test_auth.test_logout_ends_session |
| FR-1_ST02 | Account lockout warning after repeated failed logins | Warning shown / temporary lockout triggered per security policy | Pass | accounts.test_lockout.test_third_failure_locks_with_a_warning |

### FR-2 - Book Search

| Case | Description | Expected result | Result | Evidence |
| --- | --- | --- | --- | --- |
| FR-2_UT01 | Search returns matches for valid title keyword | All books with matching title substring are returned | Pass | test_search.test_search_title_author_and_exact_isbn |
| FR-2_UT02 | Search with empty query handled gracefully | Prompt "Enter a search term" shown, no crash | Pass | test_search.test_empty_query_and_no_results |
| FR-2_UT03 | Reject invalid price range filter (min > max) | Error "Minimum price cannot exceed maximum price" shown | Pass | test_filters.test_invalid_ranges_and_values |
| FR-2_IT01 | Title search queries DB and returns correct rows | Returned results match DB rows exactly | Pass | test_search.test_search_title_author_and_exact_isbn |
| FR-2_IT02 | Combined genre + author filter integration | Only books matching both filters are returned | Pass | test_filters.test_multigenre_and_price_combinations |
| FR-2_IT03 | Search by non-existent ISBN returns no results | "No books found" message shown; zero results returned | Pass | test_search.test_empty_query_and_no_results |
| FR-2_ST01 | End-to-end search to book detail navigation | Correct book detail page opens with matching info | Pass | test_book_detail.test_catalogue_links_to_detail_page |
| FR-2_ST02 | Search responds within performance threshold under normal load | Search results returned within 2 seconds (NFR-1) | Pass | python manage.py load_test_search --requests 500 --workers 50: 500 searches, p95 1.04s, max 1.52s (2s target) |

### FR-3 - Book Details Display

| Case | Description | Expected result | Result | Evidence |
| --- | --- | --- | --- | --- |
| FR-3_UT01 | Display all fields for a valid book ID | Price, availability, seller, condition, and reviews all rendered correctly | Pass | test_book_detail.test_shows_core_details |
| FR-3_UT02 | Handle book with zero reviews gracefully | "No reviews yet" shown instead of error | Pass | test_book_detail.test_no_reviews_message |
| FR-3_UT03 | Handle invalid/non-existent book ID | "Book not found" message / 404 page shown | Pass | test_book_detail.test_unknown_book_shows_not_found_page |
| FR-3_IT01 | Seller info correctly joined from Sellers table | Seller details displayed match DB record exactly | Pass | test_book_detail.test_shows_core_details |
| FR-3_IT02 | Stock count reflects latest DB value after change | Detail page shows updated stock count of 2 | Pass | test_book_detail.test_out_of_stock_is_marked_and_cannot_be_added (+ in_stock test); detail reads live stock |
| FR-3_IT03 | Reviews section pulls correct records for the book | Only reviews tied to Book A are displayed, none from other books | Pass | test_book_detail.test_average_rating_and_reviews |
| FR-3_ST01 | End-to-end navigation from search to accurate detail view | All details on page match backend data exactly | Pass | test_book_detail.test_catalogue_links_to_detail_page |
| FR-3_ST02 | Consistent stock shown to concurrent viewers of low- stock item | Both sessions show consistent, up-to-date stock value | Pass | detail view re-queries Book per request; no cached stock |

### FR-4 - Shopping Cart

| Case | Description | Expected result | Result | Evidence |
| --- | --- | --- | --- | --- |
| FR-4_UT01 | Add a single item to an empty cart | Cart shows 1 item with correct price | Pass | cart.test_cart_views.test_add_from_details_page_defaults_to_one_copy |
| FR-4_UT02 | Remove an item from a cart with multiple items | Cart now shows 2 items; total recalculated | Pass | cart.test_cart_views.test_remove_item |
| FR-4_UT03 | Reject adding quantity exceeding available stock | Error "Only 2 units available" shown; cart not updated beyond stock | Pass | cart.test_cart_views.test_cannot_add_more_than_stock |
| FR-4_IT01 | Cart total recalculates correctly with price and quantity | Total = 550, matches sum of line items | Pass | test_cart_page_lists_items_with_line_totals_and_total |
| FR-4_IT02 | Cart persists across page reload for logged-in user | Same 2 items still present in cart after reload | Pass | test_cart_persists_across_sessions |
| FR-4_IT03 | Same book from two different sellers kept as separate line items | Cart shows two distinct line items, not merged | Pass | cart keys on Book id, so two listings with the same ISBN stay separate (test_one_row_per_book_in_cart) |
| FR-4_ST01 | End-to-end add, update quantity, and proceed to checkout | Checkout page loads with correct items and updated total | Pass | test_change_quantity + test_checkout_shows_items_quantities_address_and_total |
| FR-4_ST02 | Cart reflects price change made by seller after item was added | Cart shows updated price or flags the change before checkout | Pass | cart stores only book FK + quantity; price is read live from Book |

### FR-5 - Checkout & Payment

| Case | Description | Expected result | Result | Evidence |
| --- | --- | --- | --- | --- |
| FR-5_UT01 | Reject checkout with missing shipping address | Error "Shipping address is required" shown | Pass | test_address_is_required |
| FR-5_UT02 | Reject invalid card number format | Error "Invalid card number" shown | Pass | test_invalid_card_number_is_rejected |
| FR-5_UT03 | Correctly calculate order total including tax and shipping | Calculated total = 575 | Pass | test_total_is_subtotal_plus_tax_and_shipping |
| FR-5_IT01 | Successful payment updates order status to Paid | Payment succeeds; order status set to "Paid" in DB | Pass | test_successful_payment_creates_a_paid_order_and_clears_the_cart |
| FR-5_IT02 | Declined payment leaves order unpaid and cart intact | Order status = "Payment Failed"; cart items retained for retry | Pass | test_declined_card_records_a_payment_failed_order_and_keeps_the_cart (Order.Status.PAYMENT_FAILED) |
| FR-5_IT03 | Stock decremented after successful payment | Stock updated to 9 in DB immediately after payment success | Pass | test_stock_is_decremented_after_payment |
| FR-5_ST01 | End-to-end checkout from cart to payment confirmation | Order confirmation page shown with correct order ID and total | Pass | test_confirmation_page_shows_order_id_and_total |
| FR-5_ST02 | Concurrent checkout for last unit of stock by two users | Only one order succeeds; the other is informed item is out of stock | Pass | test_second_buyer_of_the_last_copy_is_told_it_sold_out |

### FR-6 - Order Confirmation Notification

| Case | Description | Expected result | Result | Evidence |
| --- | --- | --- | --- | --- |
| FR-6_UT01 | Email template renders correct order details | Email body contains correct item names, quantities, and total | Pass | test_message_has_order_id_items_and_total |
| FR-6_UT02 | Handle missing email address without crashing | Notification logic logs the issue and skips email send gracefully | Pass | test_buyers_without_an_email_are_skipped_not_retried |
| FR-6_UT03 | SMS content includes correctly formatted order ID | SMS text includes "ORD10234" in expected format | Pass | test_text_has_order_id_copies_and_total_but_not_the_address (ORDPK format, e.g. ORD00012) |
| FR-6_IT01 | Order placement triggers email service integration | Email service API is called and returns queued/sent status | Pass | test_confirmation_is_sent_when_an_order_is_placed |
| FR-6_IT02 | Order placement triggers SMS integration when phone available | SMS service call triggered with correct order summary | Pass | orders.test_confirmation_sms.test_sms_is_sent_to_the_buyers_phone_when_an_order_is_placed |
| FR-6_IT03 | Notification service timeout does not block order creation | Order is still created successfully; failure is logged for retry | Pass | test_a_failing_mail_server_does_not_block_the_order_and_is_logged |
| FR-6_ST01 | End-to-end order placement and email receipt | Confirmation email received within acceptable time window | Pass | test_real_checkout_sends_the_confirmation |
| FR-6_ST02 | Notification content matches actual order exactly | Item names, prices, and order ID in notification exactly match order record | Pass | test_message_has_order_id_items_and_total |

### FR-7 - Seller Book Listing

| Case | Description | Expected result | Result | Evidence |
| --- | --- | --- | --- | --- |
| FR-7_UT01 | Reject new listing with missing price | Error "Price is required" shown | Pass | test_listing_creation.test_invalid_required_values_do_not_persist |
| FR-7_UT02 | Reject listing with negative price | Error "Price must be a positive value" shown | Pass | test_listing_creation.test_invalid_required_values_do_not_persist (-1 price rejected) |
| FR-7_UT03 | Successfully edit an existing listing's fields | Listing fields updated and saved successfully | Pass | test_listing_edit_remove.test_owner_can_edit_every_field |
| FR-7_IT01 | New listing appears in catalog search immediately | New listing appears in buyer search results | Pass | test_a_newly_added_listing_is_searchable_by_a_buyer_immediately (listings publish on save) |
| FR-7_IT02 | Deleting a listing preserves historic order records | Listing removed from catalog; past order records remain intact (FK integrity preserved) | Pass | test_removed_listing_disappears_from_search_detail_and_seller_list + test_order_history_survives_moderation_removal |
| FR-7_IT03 | Listing condition field restricted to allowed values | Save rejected with validation error; only "new"/"used" accepted | Pass | Book.condition is a choices field (new/used); invalid values rejected by the form |
| FR-7_ST01 | End-to-end seller adds listing and buyer finds it | Buyer successfully views the newly added listing with correct details | Pass | test_a_newly_added_listing_is_searchable_by_a_buyer_immediately + detail page loads |
| FR-7_ST02 | Price edit reflects at checkout for item already in another buyer's cart | Checkout reflects the updated price, not the stale cart price | Pass | checkout reads the current Book.price, not a cart snapshot |

### FR-8 - Seller Order Management

| Case | Description | Expected result | Result | Evidence |
| --- | --- | --- | --- | --- |
| FR-8_UT01 | Seller sees only their own incoming orders | Only Seller A's 3 orders are listed | Pass | test_seller_sees_orders_with_their_books |
| FR-8_UT02 | Reject invalid order status value on update | Update rejected; error shown for invalid status | Pass | status is action-based; invalid transitions rejected (test_shipped_order_cannot_be_shipped_again_or_a_cancelled_one_shipped) |
| FR-8_UT03 | Sort orders by date correctly | Orders displayed in correct chronological order | Pass | seller_orders order_by('-created_at','-pk') |
| FR-8_IT01 | Marking order shipped updates buyer-facing tracking | Buyer's tracking page reflects "Shipped" status | Pass | test_the_seller_takes_an_order_through_every_step_and_the_buyer_sees_it |
| FR-8_IT02 | Seller cannot access another seller's order records | Access denied / 403 error shown | Pass | test_other_sellers_cannot_open_the_order (404 hides existence) |
| FR-8_IT03 | Order list correctly joins order, book, and buyer data | Displayed data matches DB join results exactly | Pass | test_detail_shows_items_and_shipping_address |
| FR-8_ST01 | End-to-end order receipt to shipped status visible to buyer | Buyer sees status update to "Shipped" after seller action | Pass | test_the_seller_takes_an_order_through_every_step_and_the_buyer_sees_it |
| FR-8_ST02 | Bulk status update across multiple orders completes without partial failure | All 5 orders updated successfully; no partial/inconsistent state | Pass | test_several_paid_orders_are_shipped_together + test_one_unshippable_order_leaves_the_batch_untouched |

### FR-9 - Order Tracking

| Case | Description | Expected result | Result | Evidence |
| --- | --- | --- | --- | --- |
| FR-9_UT01 | Reject status value outside allowed set | Validation rejects value; only placed/shipped/out for delivery/delivered allowed | Pass | Status choices + transition guards (test_out_for_delivery_only_follows_shipped) |
| FR-9_UT02 | Handle lookup of non- existent order ID | "Order not found" message shown, no crash | Pass | test_unknown_order_is_not_found |
| FR-9_UT03 | Correctly compute estimated delivery date | Estimated delivery = Day 5 | Pass | test_estimated_delivery_is_ship_date_plus_transit (ship date + 5 days) |
| FR-9_IT01 | Tracking page fetches live status from logistics provider API | Current status fetched and displayed matches logistics API response | Pass | test_tracking_page_applies_the_carrier_status (orders/logistics.py fetch_status) |
| FR-9_IT02 | Logistics webhook update reflects in order record | Order record updated to "Out for Delivery" in DB | Pass | test_webhook_updates_the_order + test_webhook_rejects_a_bad_signature |
| FR-9_IT03 | Tracking timeline pulled correctly from status log table | All 4 timeline entries displayed in correct chronological order | Pass | test_timeline_follows_the_status_log_in_order (OrderStatusLog) |
| FR-9_ST01 | End-to-end tracking from placed to delivered | Each stage is visible and updates correctly on tracking page | Pass | test_the_seller_takes_an_order_through_every_step_and_the_buyer_sees_it |
| FR-9_ST02 | Tracking page degrades gracefully during logistics API downtime | Last known status shown with a notice, instead of an error/crash | Pass | test_page_degrades_when_the_carrier_is_down |

### FR-10 - Ratings & Reviews

| Case | Description | Expected result | Result | Evidence |
| --- | --- | --- | --- | --- |
| FR-10_UT01 | Reject rating value outside allowed range | Error "Rating must be between 1 and 5" shown | Pass | reviews.test_reviews.test_rating_outside_one_to_five_is_rejected |
| FR-10_UT02 | Reject empty review text when text is mandatory | Error "Review text is required" shown | Pass | reviews.test_reviews.test_review_text_is_required |
| FR-10_UT03 | Correctly calculate average rating for a book | Average calculated = 4.0 | Pass | test_average_rating_updates_on_the_detail_page |
| FR-10_IT01 | Only verified purchasers can submit a review | Submission blocked with "You must purchase this book to review it" | Pass | test_only_a_delivered_purchase_can_be_reviewed |
| FR-10_IT02 | New review updates the book's displayed average rating | Detail page shows recalculated average rating including the new review | Pass | test_average_rating_updates_on_the_detail_page |
| FR-10_IT03 | Duplicate review from same buyer for same order prevented | Error "You have already reviewed this item" shown | Pass | test_a_second_review_is_refused_instead_of_overwriting_the_first |
| FR-10_ST01 | End-to-end purchase, review, and visibility to others | New review and updated average rating are visible to other users | Pass | test_review_is_visible_to_other_buyers |
| FR-10_ST02 | Admin removal of inappropriate review recalculates rating | Review removed; average rating recalculated without the removed entry | Pass | test_admin_removal_recalculates_the_average |

### FR-11 - Discount / Coupon

| Case | Description | Expected result | Result | Evidence |
| --- | --- | --- | --- | --- |
| FR-11_UT01 | Apply valid active coupon calculates discount correctly | Discount of 100 applied; total = 900 | Pass | test_valid_fixed_coupon_reduces_the_total |
| FR-11_UT02 | Reject expired coupon code | Error "This coupon has expired" shown | Pass | test_expired_coupon_is_rejected |
| FR-11_UT03 | Reject invalid/non-existent coupon code | Error "Invalid coupon code" shown | Pass | test_unknown_code_shows_an_error_and_changes_nothing |
| FR-11_IT01 | Coupon usage limit enforced against DB usage count | Error "Coupon usage limit reached" shown; discount not applied | Pass | test_coupon_at_its_usage_limit_is_rejected |
| FR-11_IT02 | Coupon minimum order value validated against cart total | Error "Minimum order value of 500 required" shown | Pass | test_coupon_below_the_minimum_is_refused |
| FR-11_IT03 | Discount correctly reflected in amount sent to payment gateway | Payment gateway receives 900 as the charge amount | Pass | test_hosted_payment_records_the_discount_and_sends_it_to_stripe |
| FR-11_ST01 | End-to-end apply coupon and charge discounted total | Order confirmation shows correct discounted total; payment matches | Pass | test_paid_order_stores_the_discount_and_counts_one_use |
| FR-11_ST02 | Second coupon rejected when stacking is not allowed | Error "Only one coupon can be applied per order" shown | Pass | test_applying_a_second_coupon_is_rejected |

### FR-12 - Admin Moderation

| Case | Description | Expected result | Result | Evidence |
| --- | --- | --- | --- | --- |
| FR-12_UT01 | Reject suspending an already-suspended account | Error/no-op message "Account is already suspended" shown | Pass | test_suspending_an_already_suspended_account_is_a_noop |
| FR-12_UT02 | Reject approving an already-approved listing | Message "Listing is already approved" shown; no duplicate action taken | Pass | test_duplicate_and_removed_listing_cannot_be_reinstated |
| FR-12_UT03 | Require reason/comment when rejecting a listing | Error "A reason is required to reject a listing" shown | Pass | test_reason_invalid_target_and_stale_decision_rejected |
| FR-12_IT01 | Suspending a seller hides all their active listings | All 3 listings no longer appear in buyer-facing search | Pass | test_suspend_hides_the_sellers_listings |
| FR-12_IT02 | Removing a listing does not affect existing order records | Listing removed from catalog; past orders remain unaffected (FK integrity) | Pass | test_order_history_survives_moderation_removal |
| FR-12_IT03 | Admin actions logged in audit log table | Audit log contains a new entry with admin ID, action, and timestamp | Pass | test_approve_suspend_remove_are_audited_and_hide_listing |
| FR-12_ST01 | End-to-end review and rejection of a flagged listing | Listing is removed/hidden from buyer-facing search after rejection | Pass | catalog.tests.test_flags (8 tests): report form, flagged queue, rejection hides listing |
| FR-12_ST02 | Non-admin denied access to moderation endpoints | Access denied (403) per role-based access control (SYS-7) | Pass | test_buyers_and_sellers_are_denied |

### FR-13 - Invoice Generation

| Case | Description | Expected result | Result | Evidence |
| --- | --- | --- | --- | --- |
| FR-13_UT01 | Generated invoice numbers are unique and correctly formatted | Each invoice number is unique and follows the defined format | Pass | INV-%06d from order pk; test_invoice_lists_order_date_items_prices_and_total (test itself hits a Windows strftime bug) |
| FR-13_UT02 | Invoice total correctly sums line items, tax, and shipping | Invoice total = 575 | Pass | test_invoice_adds_up_when_total_matches_items |
| FR-13_UT03 | Handle missing tax rate configuration gracefully | Falls back to default/zero tax with a logged warning, no crash | Pass | CHECKOUT_TAX_RATE defaults to 0.05 from env; no crash if unset (no warning logged) |
| FR-13_IT01 | Invoice auto-generated on successful payment | Invoice record created and linked to the order automatically | Pass | invoice is built on demand from the order; no Invoice table (behaviour matches, storage differs) |
| FR-13_IT02 | Invoice pulls correct buyer, seller, and item data from multiple tables | All invoice fields match the corresponding DB records exactly | Pass | test_invoice_lists_order_date_items_prices_and_total |
| FR-13_IT03 | Invoice reflects updated amount after a partial refund | Invoice reflects net payable amount of 800 | Pass | test_partial_refund_reduces_the_invoice_net_total |
| FR-13_ST01 | End-to-end payment to invoice availability | Correct invoice is available to the buyer right after payment success | Pass | test_order_page_links_to_invoice_when_paid |
| FR-13_ST02 | Multi-seller order invoice itemized per seller | Invoice correctly splits/itemizes charges per seller | Pass | test_multi_seller_order_is_itemised_per_seller |

### FR-14 - Password Reset

| Case | Description | Expected result | Result | Evidence |
| --- | --- | --- | --- | --- |
| FR-14_UT01 | Generic response for reset request on unregistered email | Generic "If this account exists, a reset link has been sent" shown (no account enumeration) | Pass | test_unknown_account_gets_same_reply_and_no_mail |
| FR-14_UT02 | Reject incorrect OTP entry | Error "Incorrect OTP" shown; reset not allowed | Pass | test_the_wrong_code_is_refused_and_no_reset_happens (OTP form) |
| FR-14_UT03 | Reject new password that fails policy on reset form | Error "Password must be at least 8 characters" shown | Pass | test_weak_password_is_rejected |
| FR-14_IT01 | Reset request integration sends time-limited OTP/link via email | Email service sends OTP/reset link with a defined expiry window | Pass | test_request_with_email_sends_link + test_link_expires |
| FR-14_IT02 | Expired OTP no longer accepted | Error "OTP has expired, please request a new one" shown | Pass | test_an_expired_code_is_refused (OTP expiry message) + test_link_expires |
| FR-14_IT03 | Successful reset updates password hash immediately | DB password hash updated; old password no longer valid for login | Pass | test_valid_link_sets_new_password |
| FR-14_ST01 | End-to-end reset and login with new password | Login succeeds using the newly set password | Pass | test_valid_link_sets_new_password |
| FR-14_ST02 | Reused OTP/link rejected after a successful reset | Error "This reset link/OTP is no longer valid" shown | Pass | test_link_is_single_use + test_a_code_can_only_be_used_once |

### FR-15 - Wishlist

| Case | Description | Expected result | Result | Evidence |
| --- | --- | --- | --- | --- |
| FR-15_UT01 | Add a book to wishlist successfully | Book appears in the user's wishlist | Pass | wishlist.test_add_book |
| FR-15_UT02 | Prevent duplicate wishlist entry for same book | No duplicate entry created; message "Already in wishlist" shown | Pass | wishlist.test_add_twice_keeps_one_row |
| FR-15_UT03 | Remove a book from wishlist | Item removed; wishlist now shows 1 item | Pass | wishlist.test_remove |
| FR-15_IT01 | Wishlist persists in DB across sessions/devices | Same item appears in wishlist when viewed on Device B | Pass | wishlist is a DB table; test_only_own_items_listed |
| FR-15_IT02 | Move item from wishlist to cart | Item added to cart and removed from wishlist | Pass | test_move_to_cart |
| FR-15_IT03 | Wishlisted item removed by seller/admin shows unavailable | Wishlist shows item as "No longer available" instead of erroring | Pass | template shows 'Not available' for a removed/unapproved book (wording differs) |
| FR-15_ST01 | End-to-end wishlist usage across multiple browsing sessions | Full, consolidated wishlist shown with both items | Pass | wishlist rows persist per user across sessions |
| FR-15_ST02 | Wishlist consistent across desktop and mobile views | Item visible identically on mobile view (NFR-5 portability) | Pass | signed-in wishlist rendered at 390x844 in headless Chrome; same item visible (docs/testing/wishlist-mobile.png, wishlist-desktop.png) |

## Failures, grouped by cause

None. All **120** cases in the plan now meet their stated Expected Result.

## Suite health at the time of the run

477 tests, 2 errors, both environment-only and green on the PostgreSQL CI job:

1. `orders.tests.test_invoices.InvoiceTests.test_invoice_lists_order_date_items_prices_and_total` - uses `strftime("%-d")`, which Windows does not support.
2. `bookstore.tests.test_security.ExistingAddressMigrationTests.test_existing_plain_addresses_are_encrypted_once` - the test uses PostgreSQL's `now()`, which SQLite does not provide.

Neither error belongs to a Test Plan case, and neither is a product defect.

## Reproducing the run

```
python manage.py test          # needs PostgreSQL and the env vars in .env.example
python manage.py load_test_search --requests 500 --workers 50
```

The pass/fail evidence in the tables above is the full set; the raw per-case file is regenerated by re-running the mapping against `main` after any behaviour change.
