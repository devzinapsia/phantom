import { PhantomDashboard } from "@phantom_connector/components/phantom_dashboard/phantom_dashboard";
import { patch } from "@web/core/utils/patch";
import { user } from "@web/core/user";
import { _t } from "@web/core/l10n/translation";

// Chunk size per RPC call. Same pattern as Odoo's own base_import: the
// client drives a sequential loop of bounded server calls and renders its
// own progress bar from the running total, rather than a single call that
// blocks with no feedback until thousands of records are done.
const BATCH_SIZE = 50;

patch(PhantomDashboard.prototype, {
    setup() {
        super.setup();
        this.labels.processNow = _t("Process now");
        this.state.processing = false;
        this.state.progress = null;
    },

    async onProcessNowClick() {
        this.state.processing = true;
        // Total isn't known upfront (the server also retries "error"
        // records now, not just "pending", so the dashboard's own
        // pending-only KPI counts don't match what actually gets
        // processed) -- derived instead from the first response itself
        // (done so far + remaining), which stays authoritative for the
        // rest of the loop.
        this.state.progress = { done: 0, total: 0, percent: 0 };
        try {
            let done = false;
            let total = null;
            // Running totals accumulated across every batch call this run --
            // threaded back into each call so the final one can pass the
            // true run-wide counts to the completion-summary notification
            // (the server no longer tracks this via a "since when"
            // timestamp -- see action_phantom_create_batch's docstring).
            let invoicesProcessed = 0;
            let invoicesError = 0;
            let receiptsProcessed = 0;
            let receiptsError = 0;
            while (!done) {
                const result = await this.orm.call(
                    "res.company",
                    "action_phantom_create_batch",
                    [[user.activeCompany.id]],
                    {
                        batch_size: BATCH_SIZE,
                        invoices_processed: invoicesProcessed,
                        invoices_error: invoicesError,
                        receipts_processed: receiptsProcessed,
                        receipts_error: receiptsError,
                    }
                );
                invoicesProcessed = result.invoices_processed;
                invoicesError = result.invoices_error;
                receiptsProcessed = result.receipts_processed;
                receiptsError = result.receipts_error;
                this.state.progress.done += result.processed;
                if (total === null) {
                    total = this.state.progress.done + result.remaining;
                    this.state.progress.total = total;
                }
                this.state.progress.percent = total
                    ? Math.min(100, Math.round((100 * this.state.progress.done) / total))
                    : 100;
                done = result.done || result.processed === 0;
            }
            this.notification.add(_t("Phantom document creation finished"), { type: "success" });
            await this.fetchData();
        } finally {
            this.state.processing = false;
            this.state.progress = null;
        }
    },
});
