const video = document.querySelector("video");
const copy_link_btn = document.querySelector('.copy_link');
const create_qr_btn = document.querySelector('.create_qr');

let hrf = window.location.href;
let rid = hrf.slice(hrf.slice(0, -5).lastIndexOf('/')+1, -1);

// Connect to FastAPI WebSocket using the WS_URL and JWT_TOKEN injected in room.html
let socket = new WebSocket(`${WS_URL}/room/${rid}?token=${JWT_TOKEN}`);

let qrCode;

video.onpause = function() {
    socket.send(JSON.stringify({
        type: "broadcast", 
        data: {'status': 'paused', 'time': video.currentTime}
    }));
}

video.onplay = function() {
    socket.send(JSON.stringify({
        type: "broadcast", 
        data: {'status': 'playing', 'time': video.currentTime}
    }));
}

socket.onopen = function() {
    console.log("Connected to room", rid);
};

socket.onmessage = function(event) {
    let msg = JSON.parse(event.data);
    
    // Ignore internal connection acks
    if (msg.status === "connected") return;
    
    // Unpack data from standard broadcast
    let data = msg;
    if (msg.data && msg.data.status) {
        data = msg.data;
    }

    if (data.status == 'loading') {
        video.currentTime = data.time;
        video.pause();
    }
    if (data.status == 'playing') {
        video.currentTime = data.time;
        video.play();
    }
    if (data.status == 'paused') {
        video.currentTime = data.time;
        video.pause();
    }
    if (data.status == 'skipping') {
        video.currentTime = data.time;
    }
    if (data.status == 'update_page') {
        window.location.reload();
    }
}

socket.onclose = function() {
    console.log("WebSocket disconnected.");
}

copy_link_btn.addEventListener("click", () => {
    navigator.clipboard.writeText(hrf)
        .then(() => {
        if (copy_link_btn.textContent !== 'Скопировано!') {
            const originalText = copy_link_btn.textContent;
            copy_link_btn.textContent = 'Скопировано!';
            setTimeout(() => {
                copy_link_btn.textContent = originalText;
            }, 1500);
        }
        })
        .catch(err => {
        console.log('Something went wrong', err);
        })
});

function generateQrCode(qrContent) {
    return new QRCode("qr_code", {
        text: qrContent,
        width: 256,
        height: 256,
        colorDark: "#000000",
        colorLight: "#ffffff",
        correctLevel: QRCode.CorrectLevel.H,
    });
}

create_qr_btn.addEventListener("click", function (event) {
    if (qrCode == null) {
        qrCode = generateQrCode(hrf);
    } else {
        qrCode.makeCode(hrf);
    }
    document.getElementById("qr_code_container").style = "background-color: white; height: 300px; width: 300px; display: flex; align-items: center;justify-content: center;"
});

function skip_left() {
    if (video.currentTime - 80 > 0) {
        video.currentTime = video.currentTime-80
    } else {
        video.currentTime = 0
    }
    socket.send(JSON.stringify({
        type: "broadcast", 
        data: {'status': 'skipping', 'time': video.currentTime}
    }));
};
function skip_right() {
    if (video.currentTime + 80 < video.duration) {
        video.currentTime = video.currentTime+80
    } else {
        video.currentTime = video.duration
    }
    socket.send(JSON.stringify({
        type: "broadcast", 
        data: {'status': 'skipping', 'time': video.currentTime}
    }));
};