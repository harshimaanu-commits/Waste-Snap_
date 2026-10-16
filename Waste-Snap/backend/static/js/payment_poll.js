// Payment lists (admin and company): a payment that is "processing"
// shows its live step, and the page reloads by itself when it finishes.
(function () {

    var rows = document.querySelectorAll('[data-payment-status="processing"]');

    if (!rows.length) {
        return;
    }

    function check() {

        var finished = false;

        var requests = Array.prototype.map.call(rows, function (row) {

            return fetch(row.dataset.statusUrl, {credentials: "same-origin"})
                .then(function (response) { return response.json(); })
                .then(function (data) {

                    if (data.status !== "processing") {
                        finished = true;
                        return;
                    }

                    var note = row.querySelector(".live-stage");

                    if (note) {
                        note.textContent = "Step " + (data.stage + 1)
                            + " of " + data.total_stages + ": "
                            + data.steps[Math.min(data.stage, data.steps.length - 1)].label;
                    }
                });
        });

        Promise.all(requests).then(function () {

            if (finished) {
                window.location.reload();
            }
            else {
                setTimeout(check, 1200);
            }
        }).catch(function () {
            setTimeout(check, 2500);
        });
    }

    check();

})();
