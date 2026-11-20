USE [LMS];
GO

SET ANSI_NULLS ON;
SET QUOTED_IDENTIFIER ON;
GO

-- ==============================================================================
-- Production Performance & Concurrency Index Suite for EduPlatform LMS
-- Eliminates table scans during student logins, course browsing, lesson progression,
-- and quiz option evaluation.
-- ==============================================================================

-- 1. Prevent duplicate active enrollments and accelerate course-level lookups
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'UQ_Enrollments_Student_Course' AND object_id = OBJECT_ID('dbo.Enrollments'))
BEGIN
    PRINT 'Creating filtered unique index UQ_Enrollments_Student_Course...';
    CREATE UNIQUE NONCLUSTERED INDEX UQ_Enrollments_Student_Course
    ON dbo.Enrollments (StudentId, CourseId)
    INCLUDE (Status, ExpiryDate, CompletionPercentage, EnrollmentDate)
    WHERE Status != 'Cancelled';
END
GO

-- 2. Prevent duplicate lesson progress records and accelerate progress calculation
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'UQ_LessonProgress_Student_Lesson' AND object_id = OBJECT_ID('dbo.LessonProgress'))
BEGIN
    PRINT 'Creating unique index UQ_LessonProgress_Student_Lesson...';
    CREATE UNIQUE NONCLUSTERED INDEX UQ_LessonProgress_Student_Lesson
    ON dbo.LessonProgress (StudentId, LessonId)
    INCLUDE (IsCompleted, CompletedDate, LastAccessedDate);
END
GO

-- 3. Covering index for instant quiz option evaluation (avoids key lookups)
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_QuestionOptions_QuestionId_IsCorrect' AND object_id = OBJECT_ID('dbo.QuestionOptions'))
BEGIN
    PRINT 'Creating covering index IX_QuestionOptions_QuestionId_IsCorrect...';
    CREATE NONCLUSTERED INDEX IX_QuestionOptions_QuestionId_IsCorrect
    ON dbo.QuestionOptions (QuestionId, IsCorrect)
    INCLUDE (OptionText, OptionOrder);
END
GO

-- 4. Index on Lessons for fast module traversal
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_Lessons_Module_Order' AND object_id = OBJECT_ID('dbo.Lessons'))
BEGIN
    PRINT 'Creating index IX_Lessons_Module_Order...';
    CREATE NONCLUSTERED INDEX IX_Lessons_Module_Order
    ON dbo.Lessons (ModuleId, LessonOrder)
    INCLUDE (Title, DurationInMinutes, IsPreview);
END
GO

-- 5. Index on Modules for fast course curriculum rendering
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_Modules_Course_Order' AND object_id = OBJECT_ID('dbo.Modules'))
BEGIN
    PRINT 'Creating index IX_Modules_Course_Order...';
    CREATE NONCLUSTERED INDEX IX_Modules_Course_Order
    ON dbo.Modules (CourseId, ModuleOrder)
    INCLUDE (ModuleName);
END
GO

PRINT 'Performance index tuning applied successfully.';
GO
