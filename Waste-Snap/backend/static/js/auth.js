// Show / hide the password when the eye button is clicked
document.querySelectorAll("[data-toggle-password]").forEach(function (button) {

    button.addEventListener("click", function () {

        var input = document.getElementById(button.dataset.togglePassword);
        var icon = button.querySelector("i");

        var show = input.type === "password";

        input.type = show ? "text" : "password";

        icon.className = show ? "fa-solid fa-eye-slash" : "fa-solid fa-eye";
    });
});
