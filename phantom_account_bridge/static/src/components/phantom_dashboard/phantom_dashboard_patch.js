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
        const total =
            (this.state.data.invoices_pending_count || 0) +
            (this.state.data.receipts_pending_count || 0);
        this.state.progress = { done: 0, total, percent: total ? 0 : 100 };
        try {
            let done = total === 0;
            while (!done) {
                const result = await this.orm.call(
                    "res.company",
                    "action_phantom_create_batch",
                    [[user.activeCompany.id]],
                    { batch_size: BATCH_SIZE }
                );
                this.state.progress.done += result.processed;
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
