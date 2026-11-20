using System;
using System.Data.Entity;
using System.Threading.Tasks;
using System.Web.Mvc;
using LMS.Data;
using LMS.Services;
using Microsoft.AspNet.Identity;

namespace LMS.Controllers
{
    [Authorize]
    public class CertificateController : Controller
    {
        private readonly ApplicationDbContext _db;
        private readonly CertificateService _certificateService;

        public CertificateController()
        {
            _db = new ApplicationDbContext();
            _certificateService = new CertificateService(_db);
        }

        public CertificateController(ApplicationDbContext db, CertificateService certificateService)
        {
            _db = db;
            _certificateService = certificateService;
        }

        // GET: Certificate/ViewCertificate/5
        [HttpGet]
        public async Task<ActionResult> ViewCertificate(int id)
        {
            // BOLA / IDOR Verification: Verify user ownership or educator authorization
            var cert = await _db.Certificates
                .Include(c => c.Course)
                .FirstOrDefaultAsync(c => c.CertificateId == id);

            if (cert == null)
            {
                return HttpNotFound("The requested certificate record does not exist.");
            }

            string currentUserId = User.Identity.GetUserId();
            bool isStudentOwner = cert.StudentId == currentUserId;
            bool isAdmin = User.IsInRole("Admin");
            bool isCourseInstructor = User.IsInRole("Instructor")
                                   && cert.Course != null
                                   && cert.Course.InstructorId == currentUserId;

            if (!isStudentOwner && !isAdmin && !isCourseInstructor)
            {
                return new HttpStatusCodeResult(403, "Access Denied: You do not have permission to view this certificate.");
            }

            var model = _certificateService.GetCertificateViewModel(id);
            if (model == null) return HttpNotFound();

            return View(model);
        }

        // GET: Certificate/DownloadPdf/5
        [HttpGet]
        public async Task<ActionResult> DownloadPdf(int id)
        {
            // Consistent Authorization Check across View and Download
            var cert = await _db.Certificates
                .Include(c => c.Course)
                .FirstOrDefaultAsync(c => c.CertificateId == id);

            if (cert == null)
            {
                return HttpNotFound("The requested certificate record does not exist.");
            }

            string currentUserId = User.Identity.GetUserId();
            bool isStudentOwner = cert.StudentId == currentUserId;
            bool isAdmin = User.IsInRole("Admin");
            bool isCourseInstructor = User.IsInRole("Instructor")
                                   && cert.Course != null
                                   && cert.Course.InstructorId == currentUserId;

            if (!isStudentOwner && !isAdmin && !isCourseInstructor)
            {
                return new HttpStatusCodeResult(403, "Access Denied: You do not have permission to download this certificate.");
            }

            var model = _certificateService.GetCertificateViewModel(id);
            if (model == null) return HttpNotFound();

            // Rotativa ViewAsPdf renders in-memory via stdin stream into wkhtmltopdf
            // Eliminates loopback HTTP 302 login redirects under [Authorize]
            return new Rotativa.ViewAsPdf("CertificatePdf", model)
            {
                FileName = $"Certificate-{model.CertificateNumber}.pdf",
                PageOrientation = Rotativa.Options.Orientation.Landscape,
                PageSize = Rotativa.Options.Size.A4,
                PageMargins = new Rotativa.Options.Margins(5, 5, 5, 5)
            };
        }

        // GET: Certificate/DownloadCertificate/5 (Alias route)
        [HttpGet]
        public async Task<ActionResult> DownloadCertificate(int id)
        {
            return await DownloadPdf(id);
        }

        // GET: Certificate/Verify?certNumber=LMS-2026-123456
        [HttpGet]
        [AllowAnonymous]
        public ActionResult Verify(string certNumber = null, string certificateNumber = null, string id = null)
        {
            var target = !string.IsNullOrWhiteSpace(certificateNumber)
                ? certificateNumber
                : (!string.IsNullOrWhiteSpace(certNumber) ? certNumber : id);

            if (target == null)
            {
                return View("VerifyCertificate");
            }

            if (string.IsNullOrWhiteSpace(target))
            {
                ViewBag.ErrorMessage = "Please provide a valid certificate number.";
                return View("VerifyCertificate");
            }

            var cert = _certificateService.GetCertificateByNumber(target.Trim());
            if (cert == null)
            {
                ViewBag.ErrorMessage = $"Certificate #{target.Trim()} was not found or is invalid.";
                return View("VerifyCertificate");
            }

            var model = _certificateService.GetCertificateViewModel(cert.CertificateId);
            return View("ViewCertificate", model);
        }

        // GET: Certificate/VerifyCertificate?certificateNumber=LMS-2026-123456
        [HttpGet]
        [AllowAnonymous]
        public ActionResult VerifyCertificate(string certNumber = null, string certificateNumber = null, string id = null)
        {
            return Verify(certNumber, certificateNumber, id);
        }

        protected override void Dispose(bool disposing)
        {
            if (disposing)
            {
                _db?.Dispose();
            }
            base.Dispose(disposing);
        }
    }
}
