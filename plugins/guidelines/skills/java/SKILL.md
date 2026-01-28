---
name: java
description: Java 코딩 가이드라인. Java 코드를 작성하거나 수정할 때 이 규칙을 따릅니다.
---

# Java 코딩 가이드라인

Java 코드를 작성할 때 다음 규칙을 준수합니다.

## 들여쓰기

- 들여쓰기는 **공백 4칸**을 사용합니다.
- 탭(Tab) 문자는 사용하지 않습니다.

## 문자열 처리

문자열이 null인지, 빈 문자열인지 비교할 때에는 **Apache Commons Lang3의 StringUtils**를 적극 활용합니다.

```java
// 권장
import org.apache.commons.lang3.StringUtils;

if (StringUtils.isEmpty(str)) { ... }      // null 또는 빈 문자열
if (StringUtils.isNotEmpty(str)) { ... }   // null이 아니고 비어있지 않음
if (StringUtils.isBlank(str)) { ... }      // null, 빈 문자열, 공백만 있는 경우
if (StringUtils.isNotBlank(str)) { ... }   // null이 아니고 공백이 아닌 문자 포함

// 지양
if (str == null || str.isEmpty()) { ... }
if (str != null && !str.isEmpty()) { ... }
```

## 컬렉션 처리

빈 List나 Collection을 확인할 때에는 **Apache Commons Collections의 CollectionUtils**를 사용합니다.

```java
// 권장
import org.apache.commons.collections4.CollectionUtils;

if (CollectionUtils.isEmpty(list)) { ... }     // null 또는 비어있음
if (CollectionUtils.isNotEmpty(list)) { ... }  // null이 아니고 비어있지 않음

// 지양
if (list == null || list.isEmpty()) { ... }
if (list != null && !list.isEmpty()) { ... }
```

## 데이터베이스 쿼리

`@Query` 어노테이션 사용을 지양하고, **Querydsl의 queryFactory**를 활용합니다.

```java
// 지양: @Query 어노테이션 사용
@Query("SELECT u FROM User u WHERE u.status = :status AND u.createdAt > :date")
List<User> findActiveUsers(@Param("status") String status, @Param("date") LocalDateTime date);

// 권장: Querydsl queryFactory 사용
public List<User> findActiveUsers(String status, LocalDateTime date) {
    return queryFactory
        .selectFrom(user)
        .where(
            user.status.eq(status),
            user.createdAt.gt(date)
        )
        .fetch();
}
```
