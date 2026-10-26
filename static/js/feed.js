document.querySelectorAll('#feed-form [data-autosubmit]').forEach(function (input) {
    input.addEventListener('change', function () {
        input.form.submit();
    });
});