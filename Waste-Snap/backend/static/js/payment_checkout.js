// Checkout page: show only the panel of the chosen payment method,
// format the card number, and fill demo test values.
(function () {

    var form = document.getElementById("checkout");

    if (!form) {
        return;
    }

    var radios = form.querySelectorAll('input[name="method"]');
    var panels = form.querySelectorAll(".method-panel");

    // Show one panel; only its fields are "required"
    function showPanel(method) {

        panels.forEach(function (panel) {

            var active = panel.dataset.panel === method;

            panel.style.display = active ? "block" : "none";

            panel.querySelectorAll("input").forEach(function (input) {
                input.required = active;
            });
        });
    }

    function chosen() {

        var checked = form.querySelector('input[name="method"]:checked');

        return checked ? checked.value : "upi";
    }

    radios.forEach(function (radio) {
        radio.addEventListener("change", function () {
            showPanel(chosen());
        });
    });

    showPanel(chosen());

    // Card number: groups of 4 digits
    var number = document.getElementById("card_number");

    if (number) {
        number.addEventListener("input", function () {

            var digits = number.value.replace(/\D/g, "").slice(0, 19);

            number.value = digits.replace(/(.{4})/g, "$1 ").trim();
        });
    }

    // Expiry: MM/YY
    var expiry = document.getElementById("card_expiry");

    if (expiry) {
        expiry.addEventListener("input", function () {

            var digits = expiry.value.replace(/\D/g, "").slice(0, 4);

            expiry.value = digits.length > 2
                ? digits.slice(0, 2) + "/" + digits.slice(2)
                : digits;
        });
    }

    // "Fill a working / failing test" buttons
    form.querySelectorAll("[data-fill]").forEach(function (button) {

        button.addEventListener("click", function () {

            var values = JSON.parse(button.dataset.fill);

            Object.keys(values).forEach(function (name) {

                var field = form.querySelector('[name="' + name + '"]');

                if (field) {
                    field.value = values[name];
                    field.dispatchEvent(new Event("input"));
                }
            });
        });
    });

})();
