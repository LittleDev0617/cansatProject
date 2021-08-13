var url = `http://${document.domain}:${location.port}`
var socket = io.connect(url)
console.log(`[server info] ${url}`)

var form = $('form').on('submit', function( e ) {
  sendMsg();
})

socket.on('connect', function() {
  console.log(`[server info] ${url}`);
  socket.emit('message', 'I\'m connected!');
})

socket.on('disconnect', function(){
  console.log('disconnected')
})

socket.on('message', function(msg) {
  console.log(msg);
})

function sendMsg() {
  console.log('send message to server')
  socket.emit('message', 'test message')
}

socket.on('current_time', function(msg) {
  console.log(msg);
})