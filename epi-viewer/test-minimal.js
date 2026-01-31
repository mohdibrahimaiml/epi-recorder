const { app, BrowserWindow } = require('electron');

console.log('Electron version:', process.versions.electron);
console.log('Node version:', process.versions.node);
console.log('app object:', typeof app);

if (!app) {
    console.error('ERROR: app is undefined!');
    console.log('Full electron:', require('electron'));
    process.exit(1);
}

app.whenReady().then(() => {
    const win = new BrowserWindow({
        width: 800,
        height: 600
    });

    win.loadURL('data:text/html,<h1>Hello World</h1>');

    console.log('Window created successfully!');
});

app.on('window-all-closed', () => {
    app.quit();
});

