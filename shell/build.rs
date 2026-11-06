fn main() {
    println!("cargo:rerun-if-changed=../ui/jarvis.ico");
    println!("cargo:rerun-if-changed=../VERSION");
    if std::env::var("CARGO_CFG_TARGET_OS").as_deref() == Ok("windows") {
        let ver = std::fs::read_to_string("../VERSION").unwrap_or_else(|_| "1.0.0".into());
        let ver = ver.trim().to_string();
        let mut res = winresource::WindowsResource::new();
        res.set_icon("../ui/jarvis.ico") // id 1 — значок exe, окна и панели задач
            .set("FileDescription", "Oswin")
            .set("ProductName", "Oswin")
            .set("CompanyName", "Arsenii Minailov")
            .set("LegalCopyright", "© Arsenii Minailov")
            .set("OriginalFilename", "Oswin.exe")
            .set("FileVersion", &ver)
            .set("ProductVersion", &ver);
        res.compile().expect("resources");
    }
}
