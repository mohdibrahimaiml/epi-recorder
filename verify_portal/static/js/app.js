(function(){"use strict";
var hb=document.querySelector(".hamburger"),mm=document.querySelector(".mobile-menu");
hb&&mm&&hb.addEventListener("click",function(){hb.classList.toggle("active");mm.classList.toggle("active")});
mm&&mm.querySelectorAll("a").forEach(function(a){a.addEventListener("click",function(){hb.classList.remove("active");mm.classList.remove("active")})});
var nav=document.querySelector(".nav");window.addEventListener("scroll",function(){nav.classList.toggle("scrolled",window.scrollY>10)});
var cp=window.location.pathname.split("/").pop()||"index.html";document.querySelectorAll(".nav-links a").forEach(function(a){if(a.getAttribute("href")===cp)a.classList.add("active")});
var tb=document.querySelector("#hero-terminal .term-body");if(tb){var ls=tb.querySelectorAll("div");ls.forEach(function(l){l.style.opacity="0"});var ti=0;function rt(){if(ti<ls.length){ls[ti].style.opacity="1";ls[ti].style.transition="opacity .1s";ti++;setTimeout(rt,80)}}setTimeout(rt,600)}
var rvs=document.querySelectorAll(".reveal");if(rvs.length){var ro=new IntersectionObserver(function(es){es.forEach(function(e){if(e.isIntersecting){e.target.classList.add("visible");ro.unobserve(e.target)}})},{threshold:0.08,rootMargin:"0px 0px -20px 0px"});rvs.forEach(function(el){ro.observe(el)})}
document.querySelectorAll(".card").forEach(function(card){card.addEventListener("mousemove",function(e){var r=card.getBoundingClientRect(),x=e.clientX-r.left,y=e.clientY-r.top,cx=r.width/2,cy=r.height/2,rx=((y-cy)/cy)*-3,ry=((x-cx)/cx)*3;card.style.transform="perspective(600px) rotateX("+rx+"deg) rotateY("+ry+"deg) translateY(-3px)"});card.addEventListener("mouseleave",function(){card.style.transform="perspective(600px) rotateX(0) rotateY(0) translateY(0)"})});
})();
