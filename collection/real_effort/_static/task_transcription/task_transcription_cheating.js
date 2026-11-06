let cheat_btn = document.getElementById('cheat-btn');
if (cheat_btn) {
    cheat_btn.onclick = function() {
        liveSend({'type': 'cheat'});
    }
}

function cheat(solution) {
    input.value = solution;
}
