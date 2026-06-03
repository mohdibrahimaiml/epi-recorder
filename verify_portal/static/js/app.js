(function(){"use strict";

// ── Mobile Menu (supports both old .hamburger/.mobile-menu and new .nav-mob/.mob-menu) ──
var hb=document.querySelector(".hamburger")||document.querySelector(".nav-mob");
var mm=document.querySelector(".mobile-menu")||document.querySelector(".mob-menu");
if(hb&&mm){
  hb.addEventListener("click",function(){
    var open=mm.classList.contains("open")||mm.classList.contains("active");
    hb.classList.toggle("active");hb.classList.toggle("open");
    mm.classList.toggle("active");mm.classList.toggle("open");
    hb.setAttribute("aria-expanded",String(!open));
    document.body.style.overflow=open?"":"hidden";
  });
  mm.querySelectorAll("a").forEach(function(a){
    a.addEventListener("click",function(){
      mm.classList.remove("open","active");
      hb.classList.remove("open","active");
      hb.setAttribute("aria-expanded","false");
      document.body.style.overflow="";
    });
  });
}

// ── Nav Scroll Effect (supports both nav structures) ──
var nav=document.querySelector(".nav");
window.addEventListener("scroll",function(){
  if(nav)nav.classList.toggle("scrolled",window.scrollY>30);
});

// ── Active Nav Link ──
var cp=window.location.pathname.split("/").pop()||"index.html";
document.querySelectorAll(".nav-links a").forEach(function(a){
  if(a.getAttribute("href")===cp||a.getAttribute("href")===cp.replace(/\/$/,""))a.classList.add("active");
});

// ── Smooth Anchor Scrolling ──
document.querySelectorAll('a[href^="#"]').forEach(function(a){
  a.addEventListener("click",function(e){
    var t=document.querySelector(a.getAttribute("href"));
    if(t){
      e.preventDefault();
      t.scrollIntoView({behavior:"smooth",block:"start"});
    }
  });
});

// ── Scroll Reveal ──
if("IntersectionObserver" in window){
  var obs=new IntersectionObserver(function(entries){
    entries.forEach(function(e){
      if(e.isIntersecting){e.target.classList.add("visible");obs.unobserve(e.target)}
    });
  },{threshold:0.08,rootMargin:"0px 0px -30px 0px"});
  document.querySelectorAll(".reveal").forEach(function(el){obs.observe(el)});
}else{
  document.querySelectorAll(".reveal").forEach(function(el){el.classList.add("visible")});
}

})();
