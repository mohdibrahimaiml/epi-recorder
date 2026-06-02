(function(){"use strict";

// ── Mobile Hamburger ──
var hb=document.querySelector(".hamburger"),mm=document.querySelector(".mobile-menu");
hb&&mm&&hb.addEventListener("click",function(){
  hb.classList.toggle("active");mm.classList.toggle("active");
});
mm&&mm.querySelectorAll("a").forEach(function(a){
  a.addEventListener("click",function(){
    hb.classList.remove("active");mm.classList.remove("active");
  });
});

// ── Nav Scroll Effect ──
var nav=document.querySelector(".nav");
window.addEventListener("scroll",function(){
  nav&&nav.classList.toggle("scrolled",window.scrollY>10);
});

// ── Active Nav Link ──
var cp=window.location.pathname.split("/").pop()||"index.html";
document.querySelectorAll(".nav-links a").forEach(function(a){
  if(a.getAttribute("href")===cp)a.classList.add("active");
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

// ── Terminal Typing Animation ──
var tb=document.querySelector("#hero-terminal .term-body");
if(tb){
  var ls=tb.querySelectorAll("div");
  ls.forEach(function(l){l.style.opacity="0"});
  var ti=0;
  function rt(){
    if(ti<ls.length){
      ls[ti].style.opacity="1";
      ls[ti].style.transition="opacity .1s";
      ti++;
      setTimeout(rt,80);
    }
  }
  setTimeout(rt,600);
}

// ── Reveal on Scroll (Pramaana-style observer) ──
var rvs=document.querySelectorAll(".reveal");
if(rvs.length){
  var ro=new IntersectionObserver(function(es){
    es.forEach(function(e){
      if(e.isIntersecting){
        e.target.classList.add("visible");
        ro.unobserve(e.target);
      }
    });
  },{threshold:0.12,rootMargin:"0px 0px -40px 0px"});
  rvs.forEach(function(el){ro.observe(el)});
}

})();
