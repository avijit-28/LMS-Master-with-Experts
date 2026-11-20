USE [LMS];
GO

SET ANSI_NULLS ON;
SET QUOTED_IDENTIFIER ON;
GO

-- ==============================================================================
-- Procedure: dbo.sp_EnrollStudent
-- Purpose:   Atomically enrolls or reactivates a student in a course upon payment/assignment.
-- Concurrency: Uses MERGE ... WITH (HOLDLOCK) to prevent duplicate enrollments.
-- ==============================================================================
CREATE OR ALTER PROCEDURE dbo.sp_EnrollStudent
    @StudentId NVARCHAR(128),
    @CourseId INT
AS
BEGIN
    SET NOCOUNT ON;
    SET XACT_ABORT ON;

    BEGIN TRANSACTION;

    DECLARE @ValidityDays INT = 30;
    SELECT @ValidityDays = CASE WHEN ValidityInDays > 0 THEN ValidityInDays ELSE 30 END 
    FROM dbo.Courses WHERE CourseId = @CourseId;

    MERGE dbo.Enrollments WITH (HOLDLOCK) AS target
    USING (SELECT @StudentId AS StudentId, @CourseId AS CourseId) AS source
    ON (target.StudentId = source.StudentId AND target.CourseId = source.CourseId)
    WHEN MATCHED THEN
        UPDATE SET 
            target.Status = 'Active',
            target.ExpiryDate = DATEADD(DAY, @ValidityDays, SYSUTCDATETIME()),
            target.EnrollmentDate = SYSUTCDATETIME()
    WHEN NOT MATCHED THEN
        INSERT (StudentId, CourseId, EnrollmentDate, Status, CompletionPercentage, ExpiryDate)
        VALUES (source.StudentId, source.CourseId, SYSUTCDATETIME(), 'Active', 0.00, DATEADD(DAY, @ValidityDays, SYSUTCDATETIME()));

    COMMIT TRANSACTION;
END;
GO
