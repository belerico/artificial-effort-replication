let cheat_btn = document.getElementById('cheat-btn');
if (cheat_btn) {
    cheat_btn.onclick = function() {
        liveSend({'type': 'cheat'});
    }
}

function cheat(solution) {
    // solution is JSON like "[3.7, 6.3]", format as "3.7 6.3"
    let nums = JSON.parse(solution);
    input.value = nums.join(' ');
}
