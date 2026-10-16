// Live payment screen: asks the server for the payment's state about
// once a second and redraws the steps, the progress bar and the timeline.
(function () {

    var root = document.getElementById("live");

    if (!root) {
        return;
    }

    var statusUrl = root.dataset.statusUrl;
    var receiptUrl = root.dataset.receiptUrl;
    var retryUrl = root.dataset.retryUrl;

    var stepsList = document.getElementById("steps");
    var log = document.getElementById("log");
    var bar = document.getElementById("bar");
    var result = document.getElementById("result");

    var built = false;

    // Small helper: make an element with text (text is never treated as HTML)
    function make(tag, className, text) {

        var element = document.createElement(tag);

        if (className) {
            element.className = className;
        }

        if (text !== undefined && text !== null) {
            element.textContent = text;
        }

        return element;
    }

    function buildSteps(steps) {

        stepsList.innerHTML = "";

        steps.forEach(function (step) {

            var item = make("li", "step step-wait");
            var dot = make("span", "dot");
            var body = make("div");

            body.appendChild(make("strong", "", step.label));
            body.appendChild(make("small", "step-note", ""));

            item.appendChild(dot);
            item.appendChild(body);

            stepsList.appendChild(item);
        });

        built = true;
    }

    function drawSteps(data) {

        var items = stepsList.children;

        for (var i = 0; i < items.length; i++) {

            var item = items[i];
            var note = item.querySelector(".step-note");
            var dot = item.querySelector(".dot");

            var state = "wait";
            var text = "";
            var icon = "";

            if (i < data.stage) {
                state = "done";
                text = data.steps[i].done;
                icon = "✓";
            }
            else if (i === data.stage && data.status === "processing") {
                state = "active";
                text = "In progress...";
            }
            else if (i === data.stage && data.status === "failed") {
                state = "failed";
                text = data.failure_reason || "Failed";
                icon = "✕";
            }

            item.className = "step step-" + state;
            note.textContent = text;
            dot.textContent = icon;
        }
    }

    function drawBar(data) {

        var percent = 0;

        if (data.status === "paid") {
            percent = 100;
        }
        else if (data.status === "processing") {
            percent = (data.stage + 0.5) / data.total_stages * 100;
        }
        else {
            percent = data.stage / data.total_stages * 100;
        }

        bar.style.width = percent + "%";
        bar.className = "progress-bar"
            + (data.status === "failed" ? " progress-failed" : "")
            + (data.status === "paid" ? " progress-paid" : "");
    }

    function drawLog(data) {

        log.innerHTML = "";

        data.events.forEach(function (event) {

            var item = make("li", "timeline-" + event.kind);

            item.appendChild(make("span", "muted small", event.time + " "));
            item.appendChild(document.createTextNode(event.text));

            log.appendChild(item);
        });
    }

    function drawResult(data) {

        result.innerHTML = "";

        if (data.status === "paid") {

            var box = make("div", "result result-ok");

            box.appendChild(make("h3", "", "Payment successful"));
            box.appendChild(make("p", "", "Transaction ID: " + data.txn_id));
            box.appendChild(make("p", "muted small", data.paid_at + " · " + data.method_label));

            var link = make("a", "btn", "View receipt");
            link.href = receiptUrl;

            box.appendChild(link);
            result.appendChild(box);
        }
        else if (data.status === "failed") {

            var failed = make("div", "result result-bad");

            failed.appendChild(make("h3", "", "Payment failed"));
            failed.appendChild(make("p", "", data.failure_reason || ""));

            if (retryUrl) {
                var retry = make("a", "btn", "Retry payment");
                retry.href = retryUrl;
                failed.appendChild(retry);
            }
            else {
                failed.appendChild(make("p", "muted small", "The admin can retry this payment."));
            }

            result.appendChild(failed);
        }
        else if (data.status === "pending") {

            result.appendChild(make("p", "muted", "This payment has not been started yet."));
        }
    }

    // The page heading follows the payment
    function drawTitle(data) {

        var title = document.getElementById("live-title");

        if (!title) {
            return;
        }

        title.textContent = {
            paid: "Payment complete",
            failed: "Payment failed",
            processing: "Payment in progress"
        }[data.status] || "Payment";
    }

    function draw(data) {

        if (!built) {
            buildSteps(data.steps);
        }

        drawTitle(data);

        drawSteps(data);
        drawBar(data);
        drawLog(data);
        drawResult(data);
    }

    function poll() {

        fetch(statusUrl, {credentials: "same-origin"})
            .then(function (response) { return response.json(); })
            .then(function (data) {

                draw(data);

                // keep asking while the payment is moving
                if (data.status === "processing") {
                    setTimeout(poll, 800);
                }
            })
            .catch(function () {
                setTimeout(poll, 2000);
            });
    }

    poll();

})();
