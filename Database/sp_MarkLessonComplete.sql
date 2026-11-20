USE [LMS];
GO

SET ANSI_NULLS ON;
SET QUOTED_IDENTIFIER ON;
GO

-- ==============================================================================
-- Procedure: dbo.sp_MarkLessonComplete
-- Purpose:   Atomically marks a lesson completed for an actively enrolled student,
--            recalculates course progress percentage, and returns progress metrics.
-- Concurrency: Uses MERGE ... WITH (HOLDLOCK) to prevent deadlocks and race conditions.
-- ==============================================================================
CREATE OR ALTER PROCEDURE dbo.sp_MarkLessonComplete
    @StudentId NVARCHAR(128),
    @LessonId INT
AS
BEGIN
    SET NOCOUNT ON;
    SET XACT_ABORT ON;

    BEGIN TRANSACTION;

    -- 1. Identify the parent course and module for this lesson
    DECLARE @CourseId INT;
    DECLARE @ModuleId INT;

    SELECT @CourseId = m.CourseId, @ModuleId = l.ModuleId
    FROM dbo.Lessons l
    INNER JOIN dbo.Modules m ON l.ModuleId = m.ModuleId
    WHERE l.LessonId = @LessonId;

    IF @CourseId IS NULL
    BEGIN
        ROLLBACK TRANSACTION;
        THROW 50002, 'The specified LessonId does not exist or has no parent course.', 1;
    END

    -- 2. Guard: Verify Active Student Enrollment
    IF NOT EXISTS (
        SELECT 1 FROM dbo.Enrollments 
        WHERE StudentId = @StudentId 
          AND CourseId = @CourseId 
          AND Status != 'Cancelled'
          AND (ExpiryDate IS NULL OR ExpiryDate > SYSUTCDATETIME())
    )
    BEGIN
        ROLLBACK TRANSACTION;
        THROW 50001, 'Student is not actively enrolled in the course containing this lesson.', 1;
    END

    -- 3. Atomic Upsert of Lesson Progress record (HOLDLOCK prevents concurrency races)
    MERGE dbo.LessonProgress WITH (HOLDLOCK) AS target
    USING (SELECT @StudentId AS StudentId, @LessonId AS LessonId) AS source
    ON (target.StudentId = source.StudentId AND target.LessonId = source.LessonId)
    WHEN MATCHED THEN
        UPDATE SET 
            target.IsCompleted = 1,
            target.CompletedDate = COALESCE(target.CompletedDate, SYSUTCDATETIME()),
            target.LastAccessedDate = SYSUTCDATETIME()
    WHEN NOT MATCHED THEN
        INSERT (StudentId, LessonId, IsCompleted, WatchTimeInSeconds, CompletedDate, LastAccessedDate)
        VALUES (source.StudentId, source.LessonId, 1, 0, SYSUTCDATETIME(), SYSUTCDATETIME());

    -- 4. Calculate Lesson-level progress
    DECLARE @TotalLessons INT = 0;
    DECLARE @CompletedLessons INT = 0;

    SELECT @TotalLessons = COUNT(l.LessonId)
    FROM dbo.Lessons l
    INNER JOIN dbo.Modules m ON l.ModuleId = m.ModuleId
    WHERE m.CourseId = @CourseId;

    SELECT @CompletedLessons = COUNT(lp.ProgressId)
    FROM dbo.LessonProgress lp
    INNER JOIN dbo.Lessons l ON lp.LessonId = l.LessonId
    INNER JOIN dbo.Modules m ON l.ModuleId = m.ModuleId
    WHERE m.CourseId = @CourseId 
      AND lp.StudentId = @StudentId 
      AND lp.IsCompleted = 1;

    -- 5. Calculate and persist Course Completion Percentage
    DECLARE @ProgressPct DECIMAL(5,2) = 0.00;
    IF @TotalLessons > 0
    BEGIN
        SET @ProgressPct = CAST((@CompletedLessons * 100.0) / @TotalLessons AS DECIMAL(5,2));
    END

    UPDATE dbo.Enrollments
    SET CompletionPercentage = @ProgressPct,
        Status = CASE WHEN @ProgressPct >= 100.0 THEN 'Completed' ELSE Status END,
        CompletionDate = CASE WHEN @ProgressPct >= 100.0 AND CompletionDate IS NULL THEN SYSUTCDATETIME() ELSE CompletionDate END
    WHERE StudentId = @StudentId AND CourseId = @CourseId;

    -- 6. Return updated progress metadata to LearningService.cs
    SELECT 
        @CourseId AS CourseId,
        @TotalLessons AS TotalLessons,
        @CompletedLessons AS CompletedLessons,
        @ProgressPct AS LessonCompletionPercentage;

    COMMIT TRANSACTION;
END;
GO
